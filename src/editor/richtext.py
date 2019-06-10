import wx
from wx._richtext import RichTextCtrl
from editor import event
import io
from editor.toolbar import RichTextToolbar
from collections import defaultdict
from editor.docmodel import TextStyle, Paragraph, Image, RichTextDocument,\
    RichText, FontStyle, FontWeight, CaretPosition, Selection, InsertCharacters,\
    MoveCaret, ParagraphChange, MergeParagraphWithNext, RemoveCharacters,\
    SplitElement, SplitParagraph, RemoveElement, RemoveParagraph,\
    ChangeSelection, CharacterRangeWithId, ParagraphWithId, ElementWithId,\
    InsertParagraph, InsertElement
from editor.scrolled import RowScroller
from editor.wrapping import wrap_text
from editor.textextend_utils import GetTextExtentCached, GetPartialTextExtents
from editor.util import clone_multiply_list
from contextlib import contextmanager
import collections

debug = False
"""
features i would like:
    word wrap + no word wrap, font sizes, bold, underline, bullet lists, images (float and non float).


    remaining (difficult to less difficult):
        delete selection on insert (ok)
        delete (ok)
        backspace (ok)
        do/undo (ok)
        word forward; word back  (ok)
        Ctrl+Home/End (ok)
        delete selection on delete/backspace (ok)
        extend selection with shift  (ok)
        fic insert after image bug
        fix bug on bottom (enlarge)
        fix bug on select all
        fix position on scrolling using ScrollToCaretView
        doubleclick/tripleclick
        copy/paste/cut/select all
        align left/right/center
        tabs
        change style
        export RTF?
        sync with other control


"""

CARET_WIDTH = 2

class CaretLayout():
    def __init__(self):
        self.visible = True

    def Paint(self, dc,  rect):
        if self.visible:
            dc.SetPen(wx.BLACK_PEN)
            dc.DrawRectangle(rect.X, rect.Y, rect.Width, rect.Height)


class PaintedRichtext():
    """ A Richtext (style, width and a height) with a width, height and is on only 1 line.
        It can also have a caret and a selection (with self.start_offset and self.end_offset)
    """
    def __init__(self, width, height, text, style, caret=None):
        if height ==0:
            raise Exception("height null")
        self.width = width
        self.height = height
        self.text = text
        self.style = style
        self.caret = caret
        self.text_extends = [0] + GetPartialTextExtents(self.text, self.style)
        self.selected = False
        self.start_offset = None
        self.end_offset = None

    def __repr__(self):
        return (f"PaintedRichtext<{self.width}, {self.height}, {self.text}>" )

    def Paint(self, dc, x, y):
        if self.style:
            dc.SetFont(self.style.GetWxFont())
        else:
            dc.SetFont(TextStyle().GetWxFont())
        dc.SetTextForeground(wx.Colour("black"))
        dc.DrawText(self.text, x, y)
        if debug:
            dc.SetPen(wx.RED_PEN)
            dc.DrawRectangle(x+1, y+1, self.width-2, self.height-2)
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        # A little ugly, we just draw the selection over the existing text
        if self.selected:
            start = self.start_offset if self.start_offset is not None else 0
            end = self.end_offset if self.end_offset is not None else len(self.text)
            fgcolor = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
            bgcolor = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.SetBrush(wx.Brush(bgcolor))
            dc.DrawRectangle(x+self.text_extends[start], y, self.text_extends[end]-self.text_extends[start], self.height)
            dc.SetTextForeground(fgcolor)
            dc.DrawText(self.text[start:end], x+self.text_extends[start], y)
        if self.caret is not None:
            rect = self.GetCaretRect()
            rect.Offset(x , y)
            self.caret.Paint(dc, rect)

    def SetCaret(self, caret, offset):
        self.caret = caret
        self.carret_offset = offset

    def GetCaretRect(self):
        """ returns (x,y height) """
        return wx.Rect(self.text_extends[self.carret_offset], 0, CARET_WIDTH, self.height)

    def SetSelected(self, selected, start_offset=None, end_offset=None):
        self.selected = selected
        self.start_offset = start_offset
        self.end_offset = end_offset

    def HitTest(self, x, y):
        """ Returns (offset, before_split)
        """
        if self.text == "":
            return (0, True)
        dc = wx.MemoryDC()
        dc.SetFont(self.style.GetWxFont() if self.style else TextStyle().GetWxFont())
        # Todo add Font
        text_extends = dc.GetPartialTextExtents(self.text)
        #text_extends2 = dc.GetTextExtent(self.text)
        prev_w = 0
        for i, w in enumerate(text_extends):
            if x < w:
                break
            prev_w = w
        middle = (prev_w + (w- prev_w) // 2)
        #result = HitTestResult.Before if x < middle else HitTestResult.After
        result = i if x < middle else i +1
        # Set before_split to True if we are at the end of a line
        before_split = (result == len(self.text))
        return (result, before_split)

    def CaretSectionCount(self):
        """ e.g.: the Number of caret positions - """
        return len(self.text)
        
        
class PaintedImage():
    MARGIN = 10
    def __init__(self, width, height, wx_bitmap, style):
        self.wx_bitmap = wx_bitmap
        self.style = style
        self.width = width
        self.height = height
        self.caret = None
        self.carret_offset = None
        self.selected = False

    def Paint(self, dc, x, y):
        if self.selected:
            bgcolor = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.SetBrush(wx.Brush(bgcolor))
            dc.DrawRectangle(x, y, self.width, self.height)
        dc.DrawBitmap (self.wx_bitmap, x+self.MARGIN, y+self.MARGIN)
        if self.caret is not None:
            rect = self.GetCaretRect()
            rect.Offset(x, y)
            self.caret.Paint(dc, rect)

    def HitTest(self, x, y):
        """ Returns (offset, before_split)
            Nb: Images are not split across lines so 'before_split' is just False.
        """
        if x > self.width // 2 + self.MARGIN:
            return (1, True)
        return (0, True)

    def SetCaret(self, caret, offset):
        self.caret = caret
        self.carret_offset = offset

    def GetCaretRect(self):
        dx = {0: 0, 1: self.width}[self.carret_offset]
        return wx.Rect(dx, 0, 2, self.height)

    def SetSelected(self, selected, start_offset=None, end_offset=None):
        self.selected = selected

    @classmethod
    def from_wximage(cls, image):
        bitmap = wx.Bitmap(image, 32)
        return cls(bitmap.GetWidth() + 2*cls.MARGIN, bitmap.GetHeight() + 2*cls.MARGIN, bitmap, None)


class PositionedLayout():
    """ A RichtextLayout/ImageLayout with an added relative position (x,y).
        Each ParagraphLayout can multiple PositionedLayout to form a paragraph with elements of various styles.

        rich_text_idx: index of the rich_text inside the paragraph
        split_offset: character offset from the begining of the rich_text, in case of wrapping there are multiple RichtextLayout
            per ParagraphLayout
        .
    """
    def __init__(self, x, y, layout, rich_text_idx, split_offset=0, split_offset_end=0):
        self.x = x
        self.y = y
        self.layout = layout
        self.split_offset = split_offset
        self.split_offset_end = split_offset_end
        self.rich_text_idx = rich_text_idx

    def length(self):
        return self.split_offset_end - self.split_offset

    def __repr__(self):
        return (f"Positioned<{self.x}, {self.y}, {self.split_offset}, {self.split_offset_end}, {self.layout}>" )

    def HitTest(self, x, y):
        offset, before_split = self.layout.HitTest(x - self.x, y - self.y)
        return (self.rich_text_idx, self.split_offset + offset, before_split)

    def Contains(self, x, y):
        return wx.Rect(self.x, self.y, self.layout.width, self.layout.height).Contains(x,y)

    def ContainsY(self, y):
        return self.y <= y <= self.y + self.layout.height

    def contains_offset(self, offset):
        return self.split_offset <= offset <= self.split_offset_end

    def passed_offset(self, offset):
        return self.split_offset + len(self.layout.text) < offset

    def Paint(self, dc, x, y):
        self.layout.Paint(dc, x + self.x, y + self.y)

    def SetCaret(self, caret, offset):
        #offset = caret.offset and (caret.offset - self.rich_text_offset)
        return self.layout.SetCaret(caret, offset - self.split_offset)

    def GetCaretRect(self):
        rect = self.layout.GetCaretRect()
        rect.Offset(self.x, self.y)
        return rect

    def SetSelected(self, selected, start_offset=None, end_offset=None):
        if start_offset is not None:
            start_offset -= self.split_offset
        if end_offset is not None:
            end_offset -= self.split_offset
        return self.layout.SetSelected(selected, start_offset, end_offset)


class PaintedParagraph():
    def __init__(self, paragraph_id, max_width, width=0, height=0):
        self.paragraph_id = paragraph_id
        self.max_width = max_width
        self.height = height
        self.insert_x = 0
        self.insert_y = 0
        self.fullline_height = 0
        self.lastline_height = 0
        self.elements = []
        self.lines = [[]]
        self.elements_by_id = defaultdict(list) # id => [(line, PositionedLayout) , ...]   
        self.current_line = 0
        self.paragraph_offsets = []

    def __repr__(self):
        return (f"PaintedParagraph<{self.max_width}, {self.height}>" )

    def HasSpace(self, width):
        return self.insert_x + width <= self.max_width

    def NextLine(self):
        self.insert_y += self.lastline_height
        self.fullline_height += self.lastline_height
        self.lastline_height = 0
        self.insert_x = 0
        self.height = self.fullline_height
        self.lines.append([])
        self.current_line += 1
        
    def Append(self, idx, painted_obj, split_offset=0, split_offset_end=0):
        """ Append to the last line """
        if not self.HasSpace(painted_obj.width):
            self.NextLine()
        positionned_layout = PositionedLayout(self.insert_x, self.insert_y, painted_obj, idx, split_offset, split_offset_end)
        self.lines[self.current_line].append(positionned_layout)
        self.elements_by_id[idx].append((self.current_line, positionned_layout))
        self.elements.append(positionned_layout)
        self.insert_x += painted_obj.width
        self.lastline_height = max(self.lastline_height, painted_obj.height)
        self.height = self.fullline_height + self.lastline_height
        
    def AppendFlow(self, idx, rich_text):
        """ Append an object by wrapping text, or moving images to next line if there is insufficient space"""
        if type(rich_text) is RichText:
            rich_text_offset = 0
            if rich_text.text == "":
                # For empty paragraphs
                width, height = GetTextExtentCached("a", rich_text.style)
                width = 0
                painted_obj = PaintedRichtext(width, height, "", rich_text.style)
                self.Append(idx, painted_obj, rich_text_offset, rich_text_offset)
            else:
                for text in wrap_text(rich_text.text, rich_text.style, self.max_width, first_width=self.max_width - self.insert_x ):
                    width, height = GetTextExtentCached(text, rich_text.style)

                    painted_obj = PaintedRichtext(width, height, text, rich_text.style) #rich_text_offset
                    self.Append(idx, painted_obj, rich_text_offset, rich_text_offset+len(text))
                    rich_text_offset += len(text)
        elif type(rich_text) is Image:
            # TODO: images should move to the next line if there isn't enough space
            image = wx.Image(io.BytesIO(rich_text.image_data)) #wx.BITMAP_TYPE_JPEG
            painted_obj = PaintedImage.from_wximage(image)
            self.Append(idx, painted_obj, 0, 1)


    def Paint(self, dc, x, y):
        for text in self.elements:
            text.Paint(dc, x, y)
        if debug:    
            dc.SetPen(wx.BLUE_PEN)
            dc.DrawRectangle(x+1, y+1, self.width-2, self.height-2)
        
    def SetCaret(self, caret, richtext_idx=None, offset=None, before_split=False):
        """ sets the caret on this paragraph args = (richtext_idx, offset) """
        self.GetPaintedObject(richtext_idx, offset, before_split).SetCaret(caret, offset)

    def GetCaretRect(self, richtext_idx=None, offset=None, before_split=False):
        return self.GetPaintedObject(richtext_idx, offset, before_split).GetCaretRect()

    def GetPaintedObject(self, richtext_idx=None, offset=None, before_split=False):
        """ Return a sub Element """
        matching = {}
        for line, painted_obj in self.elements_by_id[richtext_idx]:
            if painted_obj.split_offset <= offset <= painted_obj.split_offset_end:
                matching[offset == painted_obj.split_offset_end] = painted_obj
        if len(matching) == 1:
            return list(matching.values())[0]
        elif len(matching) > 1:
            return matching[before_split]
        else:
            raise Exception("Not found %s %s %s" % (richtext_idx, offset, self))

    def IterateTexts(self, start_idx=None, end_idx=None, start_offset=None, end_offset=None):
        for elm in self.elements:
            if start_idx is not None and (start_idx > elm.rich_text_idx):
                continue
            if end_offset is not None and (end_idx < elm.rich_text_idx):
                break
            #text.split_offset + len(text.text)
            if start_offset is not None and (start_idx == elm.rich_text_idx) and elm.split_offset_end < start_offset:
                continue
            if end_offset is not None and (end_idx == elm.rich_text_idx) and elm.split_offset > end_offset:
                break
            yield (elm)

    def SetSelected(self, selected, start_caret=None, end_caret=None):
        elms = list(self.IterateTexts(start_caret and start_caret.richtext_id, 
                                      end_caret and end_caret.richtext_id, 
                                      start_caret and start_caret.offset, 
                                      end_caret and end_caret.offset))
        
        if len(elms) == 1:
            elms[0].SetSelected(selected, start_caret and start_caret.offset, end_caret and end_caret.offset)
        elif len(elms) > 1:
            elms[0].SetSelected(selected, start_caret and start_caret.offset, None)
            elms[-1].SetSelected(selected, None, end_caret and end_caret.offset)
            for t in elms[1:-1]:
                t.SetSelected(selected, None, None)

    def HitTest(self, x, y):
        """ Returns (richtext_id, offset, before_split) """
        for elm in self.elements:
            if elm.Contains(x,y):
                return elm.HitTest(x, y)
        # In the empty area at the end of a line: take the last matching of the line
        for elm in reversed(self.elements):
            if elm.ContainsY(y):
                res = elm.HitTest(x, y)
                return res

    @classmethod
    def from_paragraph(cls, pos, paragraph,  max_width):
        # pos is mainly for debugging
        result = cls(pos, max_width)
        for idx, rich_text in enumerate(paragraph.rich_texts):
            result.AppendFlow(idx, rich_text)
        return result


class CaretTimer(wx.EvtHandler):
    def __init__(self, OnBlink):
        super().__init__()
        self.blink_flag = True
        self.caret_timer = wx.Timer(self)
        self.OnBlink = OnBlink
        self.Bind(wx.EVT_TIMER, self.OnCaretTimer, self.caret_timer)

    def OnCaretTimer(self, event):
        self.blink_flag = not self.blink_flag
        self.OnBlink(self.blink_flag)

    def Reset(self):
        self.caret_timer.Stop()
        self.blink_flag = True
        self.caret_timer.Start(500)
        self.OnBlink(self.blink_flag)


class PaintedParagraphDataModel():
    """ RowScroller that displays a collection of PaintedParagraph.
     """
    def __init__(self, document, max_width=0):
        self.document = document
        self.max_width = max_width

    def GetApproximateCount(self):
        return len(self.document.elements)

    def GetFirstPos(self):
        return 0

    def GetApproximatePos(self, index):
        return min(index, len(self.document.elements)-1)

    def GetApproximateIndex(self, pos):
        return pos

    def GetNextPos(self, pos):
        if pos != len(self.document.elements) -1:
            return pos + 1

    def GetPrevPos(self, pos):
        if pos != 0:
            return pos - 1

    def GetLastPos(self):
        return len(self.document.elements) -1

    def Get(self, pos):
        row = self.document.elements[pos]
        return PaintedParagraph.from_paragraph(pos, row, self.max_width)

    def SetMaxWidth(self, max_width):
        self.max_width = max_width


class PaintedParagraphDataModelWithCaret(PaintedParagraphDataModel):
    """ RowScroller that displays a collection of PaintedParagraph with Caret + Selection.
    """
    def __init__(self,  document, max_width=0):
        super().__init__(document)
        self.max_width = max_width
        self.caret = CaretLayout()
        self.caret_timer = CaretTimer(self.OnBlink)
        self.document.CARET_CHANGED.subscribe(self.OnCaretChanged)
        self.document.SELECTION_CHANGED.subscribe(self.OnSelectionChanged)
        self.caret_pos = None
        self.caret_visible = True # EnterFocus/LooseFocus

    def ShowCaret(self, show=True):
        self.caret_visible = show
        self.caret_timer.Reset()

    def OnCaretChanged(self, oldposition, position):
        if oldposition:
            self.caret.visible = False
            self.Modified(oldposition.paragraph_id)
        self.caret = CaretLayout()
        if position:
            layout_paragraph = self.GetRowCached(position.paragraph_id)
            if layout_paragraph:
                layout_paragraph.SetCaret(self.caret, position.richtext_id, position.offset, position.before_split)
            # caret_timer.Reset will Call Modified(position.paragraph_id)
            self.caret_timer.Reset()

    def OnSelectionChanged(self, old_selection, selection):
        if selection is None:
            self.caret_start = None

        modified = set()
        if old_selection:
            for pos, layout in self.IterateLayoutRows(old_selection.start.paragraph_id, old_selection.end.paragraph_id):
                layout.SetSelected(False, None, None)
                modified.add(pos)
        if selection is not None:
            for pos, layout in self.IterateLayoutRows(selection.start.paragraph_id, selection.end.paragraph_id):
                start = selection.start if selection.start.paragraph_id == pos else None
                end = selection.end if selection.end.paragraph_id == pos else None

                layout.SetSelected(True, start, end)
                modified.add(pos)
        for p in modified:
            self.Modified(p)

    def OnBlink(self, blink):
        self.caret.visible = blink and self.caret_visible
        if self.document.caret_position:
            self.Modified(self.document.caret_position.paragraph_id)

    def Get(self, pos):
        result = super().Get(pos)
        caret = self.document.GetCaretPosition()
        if caret and caret.paragraph_id == pos:
            result.SetCaret(self.caret, caret.richtext_id, caret.offset, caret.before_split)
        selection = self.document.GetSelection()
        if selection and selection.ContainsParagraph(pos):
            start = selection.start if selection.start.paragraph_id == pos else None
            end = selection.end if selection.end.paragraph_id == pos else None
            result.SetSelected(self.caret, start, end)
        return result

RICHTEXT_CTRL_DOWN = 1
RICHTEXT_SHIFT_DOWN = 2
RICHTEXT_ALT_DOWN = 4

#IGNORE_KEYS = set([wx.WXK_ESCAPE, wx.WXK_START, wx.WXK_LBUTTON, wx.WXK_RBUTTON, wx.WXK_CANCEL, wx.WXK_MBUTTON, wx.WXK_CLEAR, wx.WXK_SHIFT, wx.WXK_ALT, wx.WXK_CONTROL, wx.WXK_PAUSE, wx.WXK_CAPITAL, wx.WXK_END, wx.WXK_HOME, wx.WXK_LEFT, wx.WXK_UP, wx.WXK_RIGHT, wx.WXK_DOWN, wx.WXK_SELECT, wx.WXK_x.WXK_EXECUTE, wx.WXK_SNAPSHOT, wx.WXK_INSERT, wx.WXK_HELP, wx.WXK_F1, wx.WXK_F2, wx.WXK_F3, wx.WXK_F4, wx.WXK_F5, wx.WXK_F6, wx.WXK_F7, wx.WXK_F8, wx.WXK_F9, wx.WXK_F10, wx.WXK_F11, wx.WXK_F12, wx.WXK_F13, wx.WXK_F14, wx.WXK_F15, wx.WXK_F16, wx.WXK_F17, wx.WXK_F18, wx.WXK_F19, wx.WXK_F20, wx.WXK_F21, wx.WXK_F22, wx.WXK_F23, wx.WXK_F24, wx.WXK_NUMLOCK, wx.WXK_SCROLL, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_F1, wx.WXK_NUMPAD_F2, wx.WXK_NUMPAD_F3, wx.WXK_NUMPAD_F4, wx.WXK_NUMPAD_HOME, wx.WXK_NUMPAD_LEFT, wx.WXK_NUMPAD_UP, wx.WXK_NUMPAD_RIGHT, wx.WXK_NUMPAD_DOWN, wx.WXK_NUMPAD_PAGEUP, wx.WXK_NUMPAD_PAGEDOWN, wx.WXK_NUMPAD_END, wx.WXK_NUMPAD_BEGIN, wx.WXK_NUMPAD_INSERT, wx.WXK_WINDOWS_LEFT])
#wx.WXK_BROWSER_BACK, wx.WXK_BROWSER_FORWARD, wx.WXK_BROWSER_REFRESH, wx.WXK_BROWSER_STOP, wx.WXK_BROWSER_SEARCH, wx.WXK_BROWSER_FAVORITES, wx.WXK_BROWSER_HOME, wx.WXK_VOLUME_MUTE, wx.WXK_VOLUME_DOWN, wx.WXK_VOLUME_UP, wx.WXK_MEDIA_NEXT_TRACK, wx.WXK_MEDIA_PREV_TRACK, wx.WXK_MEDIA_STOP, wx.WXK_MEDIA_PLAY_PAUSE, wx.WXK_LAUNCH_MAIL, wx.WXK_LAUNCH_APP1, wx.WXK_LAUNCH_APP2

class CustomRichTextControl(RowScroller):
    def __init__(self, document, parent, id=wx.ID_ANY, label="", pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.NO_BORDER,
                 name="CustomRichTextControl"):
        datamodel = PaintedParagraphDataModelWithCaret(document)
        self.document = document
        super().__init__(datamodel, parent)
        self.SetBackgroundColour(wx.Colour("white"))
        self.Bind(wx.EVT_SIZE, self.OnSize2)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.EVT_MOTION, self.OnMouseMove)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.OnMouseCaptureLost)
        self.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
        self.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.Bind(wx.EVT_CHAR,self.OnChar)

        accel_tbl = wx.AcceleratorTable([
                (wx.ACCEL_CTRL,  ord('Z'), wx.ID_UNDO ),
                (wx.ACCEL_CTRL,  ord('Y'), wx.ID_REDO ),
                (wx.ACCEL_CTRL,  ord('X'), wx.ID_CUT ),
                (wx.ACCEL_CTRL,  ord('C'), wx.ID_COPY ),
                (wx.ACCEL_CTRL,  ord('V'), wx.ID_PASTE ),
                (wx.ACCEL_CTRL,  ord('A'), wx.ID_SELECTALL ),
                ])
        self.SetAcceleratorTable(accel_tbl)
        self.Bind (wx.EVT_MENU, self.OnUndo, id=wx.ID_UNDO)
        self.Bind (wx.EVT_MENU, self.OnRedo, id=wx.ID_REDO)
        self.Bind (wx.EVT_MENU, self.OnCut, id=wx.ID_CUT)
        self.Bind (wx.EVT_MENU, self.OnCopy, id=wx.ID_COPY)
        self.Bind (wx.EVT_MENU, self.OnPaste, id=wx.ID_PASTE)
        self.Bind (wx.EVT_MENU, self.OnSelectAll, id=wx.ID_SELECTALL)

        self.dragging = False
        self.caret_start = None
        self.do_stack = []

    def OnSetFocus(self, event):
        self.datamodel.ShowCaret()

    def OnKillFocus(self, event):
        self.datamodel.ShowCaret(False)

    def CaretHitTest(self, x, y):
        """ return a CaretPosition from an x,y"""
        result = self.HitTest(x, y)
        if result:
            return CaretPosition(*result)

    def WordRight(self, count, flags):
        caret = self.document.GetCaretPosition()
        self.document.SetCaret(self.document.move_word_right(caret))

    def MoveRight(self, count, flags):
        caret = self.document.GetCaretPosition()
        self.document.SetCaret(self.document.move_right(caret))

    @contextmanager
    def Navigation(self, flags):
        self.ScrollIntoCaretView()
        if not flags & RICHTEXT_SHIFT_DOWN:
            self.caret_start = None
        elif self.caret_start is None:
            self.caret_start = self.document.GetCaretPosition()
        yield
        if flags & RICHTEXT_SHIFT_DOWN:
            caret = self.document.GetCaretPosition()
            selection = Selection(self.caret_start, caret)
            if selection != self.document.GetSelection():
                print ("SetSelection", selection)
                self.document.SetSelection(selection)
        elif self.document.GetSelection() is not None:
            self.document.SetSelection(None)
        self.ScrollIntoCaretView()

    def WordLeft(self, count, flags):
        caret = self.document.GetCaretPosition()
        self.document.SetCaret(self.document.move_word_left(caret))

    def MoveLeft(self, count, flags):
        caret = self.document.GetCaretPosition()
        self.document.SetCaret(self.document.move_left(caret))

    def MoveToParagraphStart(self, flags):
        caret = self.document.GetCaretPosition()
        self.document.SetCaret(self.document.move_to_paragraph_start(caret))

    def MoveToParagraphEnd(self, flags):
        caret = self.document.GetCaretPosition()
        self.document.SetCaret(self.document.move_to_paragraph_end(caret))

    def MoveDown(self, count, flags):
        # wx.RichTextCtrl continously moves forwards when going a lot down (buggy).
        # Wordpad keeps a 'dx' in memory when going only up or down, but forgets it after left or right moves
        caret = self.document.GetCaretPosition()
        if not caret:
            return
        p = self.GetRowCached(caret.paragraph_id)
        caret_rect = p.GetCaretRect(caret.richtext_id, caret.offset, caret.before_split)
        res = self.ScrollIntoViewXY(caret.paragraph_id, caret_rect.X, caret_rect.Y+caret_rect.Height+caret_rect.Height)
        newcaret = self.CaretHitTest(caret_rect.X+self.margin, self.GetLayoutY(caret.paragraph_id) + caret_rect.Y+caret_rect.Height+2)
        if newcaret:
            self.document.SetCaret(newcaret)

    def MoveUp(self, count, flags):
        # wx.RichTextCtrl continously moves forwards when going a lot down (buggy).
        # Wordpad keeps a 'dx' in memory when going only up or down, but forgets it after left or right moves
        caret = self.document.GetCaretPosition()
        if not caret:
            return
        p = self.GetRowCached(caret.paragraph_id)
        caret_rect = p.GetCaretRect(caret.richtext_id, caret.offset, caret.before_split)
        self.ScrollIntoViewXY(caret.paragraph_id, caret_rect.X, caret_rect.Y-caret_rect.Height)
        newcaret = self.CaretHitTest(caret_rect.X+self.margin, self.GetLayoutY(caret.paragraph_id) + caret_rect.Y -2)
        if newcaret:
            self.document.SetCaret(newcaret)

    def GetCaretRect(self):
        caret = self.document.GetCaretPosition()
        if not caret:
            return
        p = self.GetRowCached(caret.paragraph_id)
        if not p:
            return
        caret_rect = p.GetCaretRect(caret.richtext_id, caret.offset, caret.before_split)
        caret_rect.Offset(self.margin, self.GetLayoutY(caret.paragraph_id))
        return caret_rect

    def ScrollIntoCaretView(self):
        caret = self.document.GetCaretPosition()
        if not caret:
            return
        row = self.GetRowCached(caret.paragraph_id)
        caret_rect = row.GetCaretRect(caret.richtext_id, caret.offset, caret.before_split)
        caret_rect.Offset(self.margin, 0)
        self.ScrollIntoRectView(caret.paragraph_id, caret_rect)

    def PageUp(self, count, flags):
        caret_rect = self.GetCaretRect()
        res = self.Scroll(-self.inner_height)
        newcaret = self.CaretHitTest(caret_rect.X, caret_rect.Y + caret_rect.Height / 2)
        if newcaret:
            self.document.SetCaret(newcaret)

    def PageDown(self, count, flags):
        caret_rect = self.GetCaretRect()
        res = self.Scroll(self.inner_height)
        newcaret = self.CaretHitTest(caret_rect.X, caret_rect.Y + caret_rect.Height / 2)
        if newcaret:
            self.document.SetCaret(newcaret)

    def MoveHome(self, flags):
        self.document.SetCaret(self.document.start_of_document())

    def MoveToLineStart(self, flags):
        caret = self.document.GetCaretPosition()
        if not caret:
            return
        # Depends on Layout. take the first after the newline
        p = self.GetRowCached(caret.paragraph_id)
        obj = p.GetPaintedObject(caret.richtext_id, caret.offset, caret.before_split)
        newcaret = caret.clone()
        newcaret.richtext_id = obj.rich_text_idx
        newcaret.offset = obj.split_offset
        newcaret.before_split = False
        self.document.SetCaret(newcaret)

    def MoveEnd(self, flags):
        self.document.SetCaret(self.document.end_of_document())

    def MoveToLineEnd(self, flags):
        caret = self.document.GetCaretPosition()
        if not caret:
            return
        p = self.GetRowCached(caret.paragraph_id)
        obj = p.GetPaintedObject(caret.richtext_id, caret.offset, caret.before_split)
        newcaret = caret.clone()
        newcaret.richtext_id = obj.rich_text_idx
        newcaret.offset = obj.split_offset_end
        newcaret.before_split = True
        self.document.SetCaret(newcaret)

    def Return(self, event):
        self.ScrollIntoCaretView()
        elm = self.document.GetCurrentElement()
        p = self.document.GetCurrentParagraph()
        if not elm:
            return
        caret = self.document.GetCaretPosition().clone()
        actions = []
        if type(elm) is RichText:
            actions.append(MoveCaret(caret.clone(), None))#  paragraph_id, element_id, offset
            actions.append(SplitElement(caret.paragraph_id, caret.richtext_id, caret.offset))#  paragraph_id, element_id, offset
            caret.richtext_id += 1
        actions.append(SplitParagraph(caret.paragraph_id, caret.richtext_id))
        actions.append(MoveCaret(None, caret.next_paragraph()))
        self.DoActions(actions)
        self.ScrollIntoCaretView()

    def GetRemoveSelectedContentActions(self):
        """ Returns (actions, new_caret)

            We set the caret left of the text removed when we are at a start of paragraph or element
            (it would be even better to do it only when the paragraph or element is deleted, but this is a detail)
            We add an paragraph + richtext when deleting everything.
        """
        selection = self.document.GetSelection()
        start, end = selection.start, selection.end
        selected_parts = reversed(list(self.document.iterate_parts(start, end)))
        actions = []
        # Set the caret left of the text removed
        # if it is at the beginning? Add an empty paragraph
        new_caret = start
        if (not self.document.is_begin_of_document(start) and
            (self.document.is_begin_of_paragraph(start) or
             self.document.is_begin_of_element(start))):
            new_caret = self.document.move_left(start, False)
        actions.append(MoveCaret(self.document.GetCaretPosition(), new_caret))
        actions.append(ChangeSelection(self.document.GetSelection(), None))
        for part in selected_parts:
            part_type = type(part)
            if part_type is CharacterRangeWithId:
                actions.append(RemoveCharacters(part.caret_start(), part.characters()))
            elif part_type is ElementWithId:
                actions.append(RemoveElement(part.paragraph_id, part.element_id, part.element))
            elif part_type is ParagraphWithId:
                actions.append(RemoveParagraph(part.paragraph_id, part.paragraph))
        if self.document.is_begin_of_document(start) and self.document.is_end_of_document(end):
            actions.append(InsertParagraph(0, Paragraph(RichText(""))))
        return actions, new_caret

    def RemoveSelectedContent(self):

        actions, caret = self.GetRemoveSelectedContentActions()
        self.DoActions(actions)
        self.ScrollIntoCaretView()

    def Backspace(self, event):
        if self.document.GetSelection():
            return self.RemoveSelectedContent()
        self.ScrollIntoCaretView()
        p = self.document.GetCurrentParagraph()
        elm = self.document.GetCurrentElement()
        caret = self.document.GetCaretPosition()
        if not elm or self.document.is_begin_of_document(caret):
            return
        actions = []
        if self.document.is_begin_of_paragraph(caret):
            new_carret = self.document.move_left(caret, one_space=False)
            actions.append(MoveCaret(caret, new_carret))
            actions.append(MergeParagraphWithNext(new_carret.paragraph_id, new_carret.richtext_id+1))
        elif self.document.is_begin_of_element(caret):
            # begin of a richtext, remove from previous richtext, keep cursor on current
            new_carret = self.document.move_left(caret)
            elm = self.document.get_element(new_carret)
            if elm.length() == 1:
                # if it becomes empty, remove it...
                actions.append(MoveCaret(caret, self.document.move_to_element_start(new_carret)))
                actions.append(RemoveElement(new_carret.paragraph_id, new_carret.richtext_id, elm))
            else:
                actions.append(RemoveCharacters(new_carret, self.document.getchar(new_carret)))
        elif caret.offset == 1 and elm.length() == 1:
            # If we are at the end a RichText, remove the richtext (images and 1 letter richtexts)
            new_carret = self.document.move_left(caret)
            new_carret = self.document.move_left(new_carret, one_space=False)
            actions.append(MoveCaret(caret, new_carret))
            actions.append(RemoveElement(caret.paragraph_id, caret.richtext_id, elm))
            # if the paragraph is now empty, merge it
            if len(p.rich_texts) == 1:
                actions.append(MergeParagraphWithNext(new_carret.paragraph_id, new_carret.richtext_id+1))
        else:
            new_carret = self.document.move_left(caret)
            actions.append(MoveCaret(caret, new_carret))
            actions.append(RemoveCharacters(new_carret, self.document.getchar(new_carret)))
        self.DoActions(actions)
        self.ScrollIntoCaretView()

    def RedrawChanges(self, changes):
        for change, idx in changes:
            if change is ParagraphChange.Modified:
                self.Modified(idx)
            elif change is ParagraphChange.Inserted:
                self.Inserted(idx)
            elif change is ParagraphChange.Removed:
                self.Removed(idx)

    def DoActions(self, actions):
        self.do_stack.append(actions)
        for action in actions:
            res = action.do(self.document)
            print (res)
            self.RedrawChanges(res)

    def Do(self, *actions):
        self.current_actions.extend(actions)
        for action in actions:
            self.RedrawChanges(action.do(self.document))

    def StartUndo(self):
        self.current_actions = []

    def EndUndo(self):
        self.do_stack.append(self.current_actions)

    def Delete(self, event):
        if self.document.GetSelection():
            return self.RemoveSelectedContent()
        p = self.document.GetCurrentParagraph()
        elm = self.document.GetCurrentElement()
        if not elm:
            return
        caret = self.document.GetCaretPosition().clone()
        actions = []
        if caret.offset == len(elm.text):
            # we are at the end a RichText, but not the end of the paragrapn so first move forward
            if caret.richtext_id < len(p.rich_texts) - 1:
                actions.append(MoveCaret(caret, caret.next_element()))
                caret = caret.next_element()
            else:
                # and also at the end of a paragraph, so merge next paragraph elements
                if caret.paragraph_id < len(self.document.elements) - 1:
                    actions.append(MergeParagraphWithNext(caret.paragraph_id, caret.richtext_id+1))
                    actions.append(MoveCaret(caret, caret.next_element()))
                    self.DoActions(actions)
                    return
            elm = self.document.elements[caret.paragraph_id].rich_texts[caret.richtext_id]
        if type(elm) is RichText:
            actions.append(RemoveCharacters(caret, elm.text[caret.offset]))
        self.DoActions(actions)

    def InsertText(self, event, flags):
        actions = []
        caret = self.document.GetCaretPosition()
        if self.document.GetSelection():
            actions, caret = self.GetRemoveSelectedContentActions()
        self.ScrollIntoCaretView()
        key = event.GetUnicodeKey()
        if key == wx.WXK_NONE:
            return
        # We use StartUndo+EndUndo here because we need multiple actions in 
        # which some depend on the preceding action result 
        self.StartUndo()
        self.Do(*actions)
        caret = self.document.GetCaretPosition()
        elm = self.document.GetCurrentElement()
        if type(elm) == RichText:
            self.Do(InsertCharacters(caret, chr(key)))
            self.Do(MoveCaret(caret, caret.move_offset(1)))
        elif type(elm) == Image:
            self.Do(InsertElement(caret.paragraph_id, caret.richtext_id + caret.offset, RichText(str(chr(key)))))
            self.Do(MoveCaret(caret, self.document.move_right(caret)))
        self.EndUndo()
        self.ScrollIntoCaretView()

    def KeyboardNavigate(self, event, flags):
        with self.Navigation(flags):
            keyCode = event.GetKeyCode()
            if keyCode == wx.WXK_RIGHT or keyCode == wx.WXK_NUMPAD_RIGHT:
                if flags & RICHTEXT_CTRL_DOWN:
                    success = self.WordRight(1, flags)
                else:
                    success = self.MoveRight(1, flags)
            elif keyCode ==  wx.WXK_LEFT or keyCode ==  wx.WXK_NUMPAD_LEFT:
                if flags & RICHTEXT_CTRL_DOWN:
                    success = self.WordLeft(1, flags)
                else:
                    success = self.MoveLeft(1, flags)
            elif keyCode == wx.WXK_UP or keyCode == wx.WXK_NUMPAD_UP:
                if flags & RICHTEXT_CTRL_DOWN:
                    success = self.MoveToParagraphStart(flags)
                else:
                    success = self.MoveUp(1, flags)
            elif keyCode == wx.WXK_DOWN or keyCode == wx.WXK_NUMPAD_DOWN:
                if flags & RICHTEXT_CTRL_DOWN:
                    success = self.MoveToParagraphEnd(flags)
                else:
                    success = self.MoveDown(1, flags)
            elif keyCode == wx.WXK_PAGEUP or keyCode == wx.WXK_NUMPAD_PAGEUP:
                success = self.PageUp(1, flags)
            elif keyCode == wx.WXK_PAGEDOWN or keyCode == wx.WXK_NUMPAD_PAGEDOWN:
                success = self.PageDown(1, flags)
            elif keyCode == wx.WXK_HOME or keyCode == wx.WXK_NUMPAD_HOME:
                if flags & RICHTEXT_CTRL_DOWN:
                    success = self.MoveHome(flags)
                else:
                    success = self.MoveToLineStart(flags)
            elif keyCode == wx.WXK_END or keyCode == wx.WXK_NUMPAD_END:
                if flags & RICHTEXT_CTRL_DOWN:
                    success = self.MoveEnd(flags)
                else:
                    success = self.MoveToLineEnd(flags)

    def OnUndo(self, event):
        if self.do_stack:
            actions = self.do_stack.pop()
            for action in reversed(actions):
                self.RedrawChanges(action.undo(self.document))

    def OnRedo(self, event):
        print ("Redo")

    def OnCut(self, event):
        print ("Cut")

    def OnCopy(self, event):
        print ("Copy")

    def OnPaste(self, event):
        print ("Paste")

    def OnSelectAll(self, event):
        self.document.SetSelection(Selection(self.document.start_of_document(), self.document.end_of_document()))

    def OnChar(self, event):
        flags = 0
        if event.CmdDown():
            flags |= RICHTEXT_CTRL_DOWN;
        if event.ShiftDown():
            flags |= RICHTEXT_SHIFT_DOWN;
        if event.AltDown():
            flags |= RICHTEXT_ALT_DOWN;
        if not event.IsKeyInCategory(wx.WXK_CATEGORY_NAVIGATION):
            self.caret_start = None
        if event.IsKeyInCategory(wx.WXK_CATEGORY_NAVIGATION):
            self.KeyboardNavigate(event, flags)
        #elif event.GetKeyCode() in (IGNORE_KEYS):
        #    return
        elif event.CmdDown():
            # Ctrl Events are handled by the AcceleratorTable
            event.Skip()
            return
        elif event.GetKeyCode() == wx.WXK_RETURN:
            self.Return(event)
        elif event.GetKeyCode() == wx.WXK_BACK:
            self.Backspace(event)
        elif event.GetKeyCode() == wx.WXK_DELETE:
            self.Delete(event)
        else:
            self.InsertText(event, flags)

    # Shift+Enter vs Enter

    def OnLeftDown(self, event):
        caret = self.CaretHitTest(*event.GetPosition())
        if caret:
            self.document.SetCaret(caret)
            self.dragging = True
            self.caret_start = caret
        event.Skip()

    def OnMouseMove(self, event):
        if self.dragging:
            caret = self.CaretHitTest(*event.GetPosition())
            if self.caret_start and caret and self.caret_start != caret:
                selection = Selection(self.caret_start, caret)
                if selection != self.document.GetSelection():
                    self.document.SetSelection(selection)
        event.Skip()

    def OnMouseCaptureLost(self, event):
        self.dragging = False # Not sure if needed

    def OnLeftUp(self, event):
        if self.dragging:
            self.dragging = False
        x, y = event.GetPosition()
        caret = self.CaretHitTest(*event.GetPosition())
        if not self.caret_start or self.caret_start == caret:
            self.document.SetSelection(None)

    def OnSize2(self, event):
        self.client_w, self.client_h = self.GetClientSize()
        self.datamodel.SetMaxWidth(self.client_w-self.margin*2)
        event.Skip()
        self.Refresh()

if __name__ == '__main__':
    class TestFrame(wx.Frame):
        def __init__(self, parent=None):
            super(TestFrame, self).__init__(parent, size=(800,600), pos=(50, 50))
            vbox = wx.BoxSizer(wx.VERTICAL)
            document = RichTextDocument(clone_multiply_list(Paragraph(RichText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde"*10)) * 1 +
                               [Paragraph(RichText("Hello", style=TextStyle(point_size=10)), RichText("World", style=TextStyle(point_size=70))),
                               Paragraph(Image(open("../sample/carpic.jpg", "rb").read())),
                               Paragraph(RichText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde", style=TextStyle(point_size=12, weight=FontWeight.Bold))),
                               Paragraph(RichText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde", style=TextStyle(style=FontStyle.Italic, underline=True)))], 1000) )
            ctrl =  CustomRichTextControl(document, self)
            vbox.Add(RichTextToolbar(self), 0, wx.EXPAND|wx.ALL)
            vbox.Add(ctrl, 3, wx.EXPAND|wx.ALL)
            rtc = RichTextCtrl(self)
            vbox.Add(rtc, 1, wx.EXPAND|wx.ALL)
            for _ in range(10):
                for a in range(1):
                    rtc.WriteText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde"*10)
                    rtc.Newline()
                rtc.WriteText("Hello")
                rtc.BeginFontSize(100)
                rtc.WriteText("World")
                rtc.EndFontSize()
                rtc.WriteImage(wx.Image(open("../sample/carpic.jpg", "rb")))
                rtc.Newline()
                rtc.BeginBold()
                rtc.BeginFontSize(12)
                rtc.WriteText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde")
                rtc.EndBold()
                rtc.EndFontSize()
                rtc.BeginItalic()
                rtc.BeginUnderline()
                rtc.WriteText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde")
                rtc.EndItalic()
                rtc.EndUnderline()

            '''
                    document = RichTextDocument((Paragraph(RichText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde"*10)) * 30 +
                                       [Paragraph(RichText("Hello", style=TextStyle(point_size=10)), RichText("World", style=TextStyle(point_size=70))),
                                       Paragraph(Image(open("carpic.jpg", "rb").read())),
                                       Paragraph(RichText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde", style=TextStyle(point_size=12, weight=FontWeight.Bold))),
                                       Paragraph(RichText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde", style=TextStyle(style=FontStyle.Italic, underline=True)))]) * 30000)
            '''
            self.SetSizer(vbox)
            self.Layout()

    app = wx.App()
    frame = TestFrame()
    frame.Show()
    app.SetTopWindow(frame)
    app.MainLoop()

