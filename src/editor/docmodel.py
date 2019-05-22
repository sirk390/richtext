import wx
from enum import Enum
from event import Event

FontWeight = Enum("FontWeight", "Normal Light Bold")
FontStyle = Enum("FontStyle", "Normal Slant Italic")
FontFamily = Enum("FontStyle", "Default Decorative Roman Script Swiss Modern")

#actions
#  inserscharachers
#  deletechar: range
#  merge paragraphs
#  split paragraph ( paragraph_index, richtext_index)
#  split richtext
    #  delete empty paragraph
    #  insert paragraph

ParagraphChange = Enum("ParagraphChange", "Modified Inserted Removed")

class Action():
    def __init__(self):
        pass
    def do(self, document):
        raise NotImplemented
    def undo(self, document):
        raise NotImplemented
    
def ReverseAction(obj):
    class result_class(obj):
        def do(self, document):
            return super().undo(document)
        def undo(self, document):
            return super().do(document)
    return result_class


class InsertCharacters(Action):
    def __init__(self, caret, characters):
        self.caret = caret
        self.characters = characters
        
    def do(self, document):
        elm = document.elements[self.caret.paragraph_id].rich_texts[self.caret.richtext_id]
        elm.insert(self.caret.offset, self.characters)
        return [(ParagraphChange.Modified, self.caret.paragraph_id)]
        
    def undo(self, document):
        elm = document.elements[self.caret.paragraph_id].rich_texts[self.caret.richtext_id]
        elm.remove(self.caret.offset, len(self.characters))
        return [(ParagraphChange.Modified, self.caret.paragraph_id)]
    
    def __repr__(self):
        return (f"<InsertCharacters {self.caret}, {self.characters}>")

class RemoveCharacters(Action):
    def __init__(self, caret, characters):
        self.caret = caret
        self.characters = characters
        
    def do(self, document):
        elm = document.elements[self.caret.paragraph_id].rich_texts[self.caret.richtext_id]
        elm.remove(self.caret.offset, len(self.characters))
        return [(ParagraphChange.Modified, self.caret.paragraph_id)]
        
    def undo(self, document):
        elm = document.elements[self.caret.paragraph_id].rich_texts[self.caret.richtext_id]
        elm.insert(self.caret.offset, self.characters)
        return [(ParagraphChange.Modified, self.caret.paragraph_id)]

    def __repr__(self):
        return (f"<RemoveCharacters {self.caret}, {self.characters}>")

class MoveCaret(Action):
    def __init__(self, old_position, new_position):
        self.old_position = old_position
        self.new_position = new_position
    def do(self, document):
        document.SetCaret(self.new_position)
        return []
    def undo(self, document):
        document.SetCaret(self.old_position)
        return []
    def __repr__(self):
        return (f"<MoveCaret {self.old_position}, {self.new_position}>")

class ChangeSelection(Action):
    def __init__(self, old_selection, new_selection):
        self.old_selection = old_selection
        self.new_selection = new_selection
    def do(self, document):
        document.SetSelection(self.new_selection)
        return []
    def undo(self, document):
        document.SetSelection(self.old_selection)
        return []
    def __repr__(self):
        return (f"<ChangeSelection {self.old_selection}, {self.new_selection}>")
    
class MergeParagraphWithNext(Action):
    def __init__(self, paragraph_id, element_id):
        self.paragraph_id = paragraph_id
        self.element_id = element_id
        
    def do(self, document):
        p = document.elements[self.paragraph_id]
        next_p = document.elements[self.paragraph_id+1]
        p.rich_texts.extend(next_p.rich_texts)
        document.RemoveParagraph(self.paragraph_id+1)
        return [(ParagraphChange.Modified, self.paragraph_id), (ParagraphChange.Removed, self.paragraph_id+1)]
    
    def undo(self, document):
        p = document.elements[self.paragraph_id]
        elements_before, elements_after = p.rich_texts[:self.element_id], p.rich_texts[self.element_id:]
        p.rich_texts = elements_before
        document.InsertParagraph(self.paragraph_id+1, Paragraph(*elements_after))
        return [(ParagraphChange.Modified, self.paragraph_id), (ParagraphChange.Inserted, self.paragraph_id+1)]
    def __repr__(self):
        act = "MergeParagraphWithNext" if type(self) is MergeParagraphWithNext else "SplitParagraph"
        return (f"<{act} {self.paragraph_id}>")

SplitParagraph = ReverseAction(MergeParagraphWithNext)


class InsertElement(Action):
    def __init__(self, paragraph_id, index, element):
        self.paragraph_id = paragraph_id
        self.index = index
        self.element = element
        
    def do(self, document):
        p = document.elements[self.paragraph_id]
        p.rich_texts = list_insert(p.rich_texts, self.index, [self.element])
        return [(ParagraphChange.Modified, self.paragraph_id)]
        
    def undo(self, document):
        p = document.elements[self.paragraph_id]
        p.rich_texts = list_remove(p.rich_texts, self.index, 1)
        return [(ParagraphChange.Modified, self.paragraph_id)]
    
    def __repr__(self):
        act = "InsertElement" if type(self) is InsertElement else "RemoveElement"
        return (f"<{act} {self.paragraph_id} {self.index}>")
RemoveElement = ReverseAction(InsertElement)


class InsertParagraph(Action):
    def __init__(self, paragraph_id, paragraph):
        self.paragraph_id = paragraph_id
        self.paragraph = paragraph
        
    def do(self, document):
        document.InsertParagraph(self.paragraph_id, self.paragraph)
        return [(ParagraphChange.Inserted, self.paragraph_id)]

    def undo(self, document):
        document.RemoveParagraph(self.paragraph_id)
        return [(ParagraphChange.Removed, self.paragraph_id)]
    
    def __repr__(self):
        act = "InsertParagraph" if type(self) is InsertElement else "RemoveParagraph"
        return (f"<{act} {self.paragraph_id}>")
    
RemoveParagraph = ReverseAction(InsertParagraph)


class MergeElementWithNext(Action):
    def __init__(self, paragraph_id, element_id, offset):
        self.paragraph_id = paragraph_id
        self.element_id = element_id
        self.offset = offset
        
    def do(self, document):
        elm = document.elements[self.paragraph_id].rich_texts[self.element_id]
        next_elm = document.elements[self.paragraph_id].rich_texts[self.element_id+1]
        elm.text = elm.text + next_elm.text
        document.elements[self.paragraph_id].RemoveElement(self.element_id+1)
        return [(ParagraphChange.Modified, self.paragraph_id)]
    
    def undo(self, document):
        elm = document.elements[self.paragraph_id].rich_texts[self.element_id]
        text_before, text_after = elm.text[:self.offset], elm.text[self.offset:]
        elm.text = text_before
        document.elements[self.paragraph_id].InsertElement(self.element_id+1, RichText(text_after))
        return [(ParagraphChange.Modified, self.paragraph_id)]
    
SplitElement = ReverseAction(MergeElementWithNext)


class TextStyle():
    def __init__(self, point_size=9, weight=FontWeight.Normal, style=FontStyle.Normal, underline=False, fontfamily=None, fontname=None):
        self.point_size = point_size
        self.weight = weight
        self.style = style
        self.underline = underline
        self.fontfamily = fontfamily
        self.fontname = fontname

    def GetWxFont(self):
        font = wx.Font(self.point_size, self.GetWxFontFamily(), self.GetWxFontStyle(), self.GetWxFontWeight(), self.underline)
        #No idea why it is not saved from above...
        font.SetPointSize(self.point_size)
        return font

    def GetWxFontFamily(self):
        if not self.fontfamily:
            return wx.DEFAULT
        return {FontFamily.Default: wx.DEFAULT, FontFamily.Decorative: wx.DECORATIVE, FontFamily.Roman: wx.ROMAN,
                FontFamily.Script: wx.SCRIPT, FontFamily.Swiss: wx.SWISS, FontFamily.Modern: wx.MODERN}[self.fontfamily]

    def GetWxFontStyle(self):
        return {FontStyle.Normal: wx.NORMAL, FontStyle.Slant: wx.SLANT, FontStyle.Italic: wx.ITALIC}[self.style]

    def GetWxFontWeight(self):
        return {FontWeight.Normal: wx.NORMAL, FontWeight.Light: wx.LIGHT, FontWeight.Bold: wx.BOLD}[self.weight]

    def clone(self):
        return TextStyle(self.point_size, self.weight, self.style, self.underline, self.fontfamily, self.fontname)


class RichTextElement():
    pass

def list_insert(lst, offset, insert_lst):
    return (lst[:offset] + insert_lst + lst[offset:])

def list_remove(lst, offset, count):
    return (lst[:offset] + lst[offset+count:])

class RichText(RichTextElement):
    def __init__(self, text, style=None):
        self.text = text
        self.style = style

    def length(self):
        return len(self.text)

    def has_offset(self, offset):
        return 0 <= offset <= len(self.text)

    def insert(self, offset, char):
        self.text = list_insert(self.text, offset, char)

    def remove(self, index, count):
        self.text = list_remove(self.text, index, count)
        
    def clone(self):
        return RichText(self.text, self.style and self.style.clone())
    
    def __repr__(self):
        return f"RichText<{self.text}, {self.style}>"



class Image(RichTextElement):
    def __init__(self, image_data, fileformat="jpg", style=None):
        self.image_data = image_data

    def length(self):
        return 1

    def has_offset(self, offset):
        return 0 <= offset <= 1

    def clone(self):
        return Image(self.image_data)

class Paragraph():
    """ A list of RichTextElement (e.g. RichText, Image...)"""
    def __init__(self, *rich_texts, style=None):
        self.rich_texts = list(rich_texts)
        self.style = style
    
    def clone(self):
        return Paragraph(*[r.clone() for r in self.rich_texts], style=self.style and self.style.clone())

    def RemoveElement(self, index):
        self.rich_texts = self.rich_texts[:index] + self.rich_texts[index+1:]
         
    def InsertElement(self, index, element):
        self.rich_texts.insert(index, element)
        
    def __mul__(self, intvalue):
        return [self.clone() for _ in range(intvalue)]

    def __repr__(self):
        return f"Paragraph<{self.rich_texts}, {self.style}>"

class CaretPosition():
    def __init__(self, paragraph_id, richtext_id, offset, before_split=False):
        """
               paragraph_id: index of the paragraph in RichTextDocument
               richtext_id: index of the RichTextElement (Paragraph or Image) in the Paragraph
               offset: caret position in the Paragraph (0 to len(paragraph)) or 0 to 1 for Images
               before_split: If the paragraph is wrapped on multiple lines, and the offset is exactly at a split,
                             before_split says to keep at the position before the split
                             It is not taken into account for comparision (it is still the same caret position, just not visually)
        """
        self.paragraph_id = paragraph_id
        self.richtext_id = richtext_id
        self.offset = offset
        self.before_split = before_split

    def __lt__(self, other):
        if self.paragraph_id != other.paragraph_id:
            return self.paragraph_id < other.paragraph_id
        if self.richtext_id != other.richtext_id:
            return self.richtext_id < other.richtext_id
        if self.offset != other.offset:
            return self.offset < other.offset

    def __eq__(self, other):
        # Nb: we don't compare before_split because it is still the same caret position
        if other is None:
            return False
        return (self.paragraph_id == other.paragraph_id and
                self.richtext_id == other.richtext_id and
                self.offset == other.offset)
        
    def clone(self):
        return CaretPosition(self.paragraph_id, self.richtext_id, self.offset, self.before_split)
    
    def move_offset(self, incr):
        return CaretPosition(self.paragraph_id, self.richtext_id, self.offset+incr, self.before_split)

    def next_element(self):
        return CaretPosition(self.paragraph_id, self.richtext_id+1, 0, self.before_split)

    def next_paragraph(self):
        return CaretPosition(self.paragraph_id+1, 0, 0, self.before_split)

    def __hash__(self):
        return hash((self.paragraph_id, self.richtext_id, self.offset))

    def __repr__(self):
        return (f"<CaretPosition: {self.paragraph_id}, {self.richtext_id}, {self.offset}, {self.before_split}>")

class Selection():
    """ Two ordered instances of 'CaretPosition' """
    def __init__(self, start, end):
        self.start, self.end =  sorted([start, end])

    def __eq__(self, other):
        if other is None:
            return False
        return (self.start == other.start and
                self.end == other.end)

    def ContainsParagraph(self, pos):
        return (self.start.paragraph_id <= pos <= self.end.paragraph_id)

    def __hash__(self):
        return hash((self.start, self.end))

    def __repr__(self):
        return (f"<Selection: {self.start}, {self.end}>")
    
class CharacterRangeWithId():
    """ Range of characters in a RichText"""
    def __init__(self, paragraph_id, element_id, element, start_offset, end_offset):
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.element = element
        self.paragraph_id = paragraph_id
        self.element_id = element_id
    
    def caret_start(self):
        return CaretPosition(self.paragraph_id, self.element_id, self.start_offset)
    
    def characters(self):
        assert type(self.element) is RichText
        return self.element.text[self.start_offset:self.end_offset]
    
    def __repr__(self):
        if type(self.element) is RichText:
            text = self.element.text[self.start_offset:self.end_offset]
        return (f"<CharacterRangeWithId: {text} {self.start_offset}, {self.end_offset}>")
    
        
class ParagraphWithId():
    """ Paragraph with its id"""
    def __init__(self, paragraph_id, paragraph):
        self.paragraph_id = paragraph_id
        self.paragraph = paragraph
        
    def __repr__(self):
        return (f"<ParagraphWithId: {self.paragraph_id}>")
    

class ElementWithId():
    def __init__(self, paragraph_id, element_id, element):
        self.paragraph_id = paragraph_id
        self.element_id = element_id
        self.element = element

    def __repr__(self):
        return (f"<ElementWithId: {self.paragraph_id} {self.element_id}>")


class RichTextDocument():
    """  List of Paragraph, with Selection and CaretPosition 
        
         A document should never contain empty elements. Empty Paragraphs are possible.
         
    """
    def __init__(self, elements, selection=None, caret_position=None):
        self.elements = elements
        self.selection = selection
        self.caret_position = caret_position

        self.CARET_CHANGED = Event()
        self.SELECTION_CHANGED = Event()

    def SetCaret(self, position):
        oldposition = self.caret_position
        self.caret_position = position
        self.CARET_CHANGED.fire(oldposition, position)

    def GetCaretPosition(self):
        return self.caret_position

    def SetSelection(self, selection):
        old_selection = self.selection 
        self.selection = selection
        self.SELECTION_CHANGED.fire(old_selection, selection)

    def GetSelection(self):
        return self.selection

    def GetCurrentParagraph(self):
        caret = self.GetCaretPosition()
        if not caret:
            return
        return self.elements[caret.paragraph_id]
    
    def GetCurrentElement(self):
        caret = self.GetCaretPosition()
        if not caret:
            return
        p = self.elements[caret.paragraph_id]
        return p.rich_texts[caret.richtext_id]
        
    def InsertParagraph(self, paragraph_id, paragraph):
        self.elements.insert(paragraph_id, paragraph)

    def RemoveParagraph(self, paragraph_id):
        self.elements = self.elements[:paragraph_id] + self.elements[paragraph_id+1:] 
    
    def get_element(self, caret):
        return self.elements[caret.paragraph_id].rich_texts[caret.richtext_id]
    
    def get_element_from_id(self, paragraph_id, richtext_id):
        return self.elements[paragraph_id].rich_texts[richtext_id]
    
    def get_paragraph(self, caret):
        return self.elements[caret.paragraph_id]
    
    def is_begin_of_document(self, caret):
        return (caret.paragraph_id == 0 and 
                caret.richtext_id == 0 and
                caret.offset == 0)

    def is_end_of_document(self, caret):
        return (caret == self.end_of_document())

    def is_begin_of_paragraph(self, caret):
        return (caret.offset == 0 and caret.richtext_id == 0)
        
    def is_begin_of_element(self, caret):
        return (caret.offset == 0)
    
    def move_to_element_start(self, caret):
        newcaret = caret.clone()
        newcaret.offset = 0
        return newcaret

    def move_to_paragraph_start(self, caret):
        newcaret = caret.clone()
        newcaret.richtext_id = 0
        newcaret.offset = 0
        return newcaret
    
    def move_to_paragraph_end(self, caret):
        newcaret = caret.clone()
        paragraph = self.elements[newcaret.paragraph_id]
        newcaret.richtext_id = len(paragraph.rich_texts) -1
        newcaret.offset = paragraph.rich_texts[newcaret.richtext_id].length()
        newcaret.before_split = True
        return newcaret
    
    def start_of_document(self):
        return CaretPosition(0, 0, 0)

    def end_of_document(self):
        last_paragraph = len(self.elements) - 1
        last_element = len(self.elements[last_paragraph].rich_texts) - 1
        last_offset = self.elements[last_paragraph].rich_texts[last_element].length()
        return CaretPosition(last_paragraph, last_element, last_offset)

    def start_of_paragraph(self, paragraph_id):
        return CaretPosition(paragraph_id, 0, 0)
    
    def end_of_paragraph(self, paragraph_id):
        last_element = len(self.elements[paragraph_id].rich_texts) - 1
        last_offset = self.elements[paragraph_id].rich_texts[last_element].length()
        return CaretPosition(paragraph_id, last_element, last_offset)
    
    def start_of_element(self, paragraph_id, element_id):
        return CaretPosition(paragraph_id, element_id, 0)
    
    def end_of_element(self, paragraph_id, element_id):
        last_offset = self.elements[paragraph_id].rich_texts[element_id].length()
        return CaretPosition(paragraph_id, element_id, last_offset)

    def move_left(self, caret, one_space=True):
        newcaret = caret.clone()
        if newcaret.offset:
            newcaret.offset -= 1
        elif newcaret.richtext_id >  0:
            newcaret.richtext_id -= 1
            paragraph = self.elements[newcaret.paragraph_id]
            newcaret.offset = paragraph.rich_texts[newcaret.richtext_id].length() - (one_space and 1 or 0)
        elif newcaret.paragraph_id >  0:
            newcaret.paragraph_id -= 1
            paragraph = self.elements[newcaret.paragraph_id]
            newcaret.richtext_id = len(paragraph.rich_texts) - 1
            newcaret.offset = paragraph.rich_texts[newcaret.richtext_id].length() - (one_space and 1 or 0)
        return newcaret
    
    def move_right(self, caret, one_space=True):
        newcaret = caret.clone()
        paragraph = self.elements[newcaret.paragraph_id]
        elm = paragraph.rich_texts[newcaret.richtext_id]
        if elm.has_offset(newcaret.offset + 1):
            newcaret.offset += 1
        elif newcaret.richtext_id + 1 < len(paragraph.rich_texts):
            newcaret.richtext_id += 1
            newcaret.offset = (one_space and 1 or 0)
        elif newcaret.paragraph_id + 1 < len(self.elements):
            newcaret.paragraph_id += 1
            newcaret.richtext_id = 0
            newcaret.offset = 0
        return newcaret

    def iterate_right(self, caret, one_space=True):
        while not self.is_end_of_document(caret):
            caret = self.move_right(caret, one_space)
            yield caret

    def iterate_left(self, caret, one_space=True):
        while not self.is_end_of_document(caret):
            caret = self.move_left(caret, one_space)
            yield caret

    def move_word_left(self, caret):
        for caret in self.iterate_left(caret, False):
            if self.is_word_start(caret) or self.is_begin_of_paragraph(caret):
                return caret
        return caret

    def is_word_start(self, caret):
        elm = self.get_element(caret)
        if type(elm) is RichText and (caret.offset > 0 and elm.text[caret.offset-1] == " "):
            return True
        return False

    def move_word_right(self, caret):
        for caret in self.iterate_right(caret, False):
            if self.is_word_start(caret) or self.is_begin_of_paragraph(caret):
                return caret
        return caret
                
    def getchar(self, caret):
        return self.elements[caret.paragraph_id].rich_texts[caret.richtext_id].text[caret.offset]

    def iterate_parts(self, start, end, yield_first_paragraph=True, yield_last_paragraph=True):
        """ yields parts as  ParagraphWithId, ElementWithId, and CharacterRangeWithId 's
            start: CaretPosition
            end: CaretPosition
        This is used for removing selection, ar changing selection style"""
        if start.paragraph_id == end.paragraph_id:
            yield from self.iterate_paragraph_parts(start.paragraph_id, start, end, False)
        else:
            yield from self.iterate_paragraph_parts(start.paragraph_id, start, None, yield_first_paragraph)
            for idx in range(start.paragraph_id+1, end.paragraph_id):
                yield ParagraphWithId(idx, self.elements[idx])
            yield from self.iterate_paragraph_parts(end.paragraph_id, None, end, yield_last_paragraph)

    def iterate_paragraph_parts(self, paragraph_id, start, end, yield_paragraph=False):
        """ yield as ParagraphWithId, ElementWithId, and CharacterRangeWithId 's """
        paragraph = self.elements[paragraph_id]
        start = start or self.start_of_paragraph(paragraph_id) 
        end = end or self.end_of_paragraph(paragraph_id) 
        if yield_paragraph and start == self.start_of_paragraph(paragraph_id) and end == self.end_of_paragraph(paragraph_id):
            yield ParagraphWithId(paragraph_id, paragraph)
        elif start.richtext_id == end.richtext_id:
            yield from self.iterate_element_parts(paragraph_id, start.richtext_id, start, end)
        else:
            yield from self.iterate_element_parts(start.paragraph_id, start.richtext_id, start, None)
            for idx in range(start.richtext_id+1, end.richtext_id):
                yield ElementWithId(paragraph_id, idx, paragraph.rich_texts[idx])
            yield from self.iterate_element_parts(end.paragraph_id, end.richtext_id, None, end)
            
    def iterate_element_parts(self, paragraph_id, element_id, start, end):
        """  yield as ElementWithId, and CharacterRangeWithId 's """
        element = self.get_element_from_id(paragraph_id, element_id)
        start = start or self.start_of_element(paragraph_id, element_id) 
        end = end or self.end_of_element(paragraph_id, element_id) 
        if start.offset == end.offset:
            return
        elif start.offset == 0 and end.offset == element.length():
            yield ElementWithId(paragraph_id, element_id, element)
        else:
            yield CharacterRangeWithId(paragraph_id, element_id, element, start.offset, end.offset)
        
            
        
    
class InlineElm():
    def __init__(self, width, heigth, text):
        self.width = width
        self.heigth = heigth
        self.text = text
