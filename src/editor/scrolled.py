import wx
from wx import MemoryDC, WXK_PAGEDOWN, WXK_PAGEUP, WXK_UP, WXK_DOWN
from _collections import deque
import random
import time
from enum import Enum
import math
from editor.event import Event
from editor.util import first
from wx.lib.newevent import NewEvent


class RowModel():
    def Paint(self, dc, x, y):
        raise NotImplemented
    def HitTest(self, x, y):
        raise NotImplemented


class DataModel():
    """ Iterator that handles a very large number of items.
        The positions can be anything defined by the implementation.
    """
    def __init__(self):
        self.MODIFIED = Event()
        self.INSERTED = Event()
        self.DELETED = Event()
    
    def Get(self, iter):
        """ Returns a RowModel """
        raise NotImplemented
    
    def GetFirst(self):
        raise NotImplemented
    
    def GetNext(self, iter):
        raise NotImplemented
    
    def GetPrev(self, iter):
        raise NotImplemented
    
    def GetLast(self):
        raise NotImplemented
    
    def GetApproximate(self, pos):
        """ pos: value between 0 and GetApproximateCount()+something  """
        raise NotImplemented
    
    def GetApproximateIndex(self, iter):
        raise NotImplemented
    
    def GetApproximateCount(self):
        raise NotImplemented

DataChange = Enum("DataChange", "Inserted Removed Modified")


class DisplayedRow():
    def __init__(self, y, end_y, rowpos, row):
        self.y = y
        self.end_y = end_y
        self.rowpos = rowpos
        self.row = row

    def __repr__(self):
        return repr((self.y, self.rowpos, self.row))

    def height(self):
        return self.end_y - self.y


RowScrollerScrolledEvent, EVT_ROWSCROLLER_SCROLLED = NewEvent()
RowScrollerDisplayChanged, EVT_ROWSCROLLER_DISPLAY_CHANGED = NewEvent()


class RowHeigths():
    def __init__(self):
        self.row_heights = {}
        
    def reset(self):
        self.row_heights = {}

    def add(self, pos, height):
        self.row_heights[pos] = height
        
    def remove(self, pos):
        del self.row_heights[pos]

    def estimate(self):    
        return sum(self.row_heights.values()) / len(self.row_heights)
 
    def reindex(self, reindex_func):   
        row_heights = {}
        for k in self.row_heights:
            row_heights[reindex_func(k)] = self.row_heights[k]
        self.row_heights = row_heights
 
    
class RowScroller(wx.Window):
    """ A VScrolledWindow that allows for pixel size scrolling
    """
    def __init__(self, datamodel, parent, id=wx.ID_ANY, label="", pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.NO_BORDER):
        super().__init__(parent)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_CHAR,self.__OnChar)
        self.Bind(wx.EVT_SCROLLWIN, self.OnScroll)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        self.line_size = 16 # Scroll this many pixels each time
        
        self.pixels_hidden_first_row = 0
        self.pixels_hidden_last_row = 0
        self.client_height = 0
        self.fixed_row = None
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.current_pos = 0
        self.margin = 8
        #above this, use scroll directly without retrieving all intermediary rows
        self.scroll_row_threshold = 500
        self.datamodel = datamodel
        self.datamodel.INSERTED.subscribe(self.OnInserted)
        self.datamodel.DELETED.subscribe(self.OnRemoved)
        self.datamodel.MODIFIED.subscribe(self.OnModified)
        
        # New
        self.displayed_rows = deque()
        self.heights = RowHeigths()
        

    def SetFixedRow(self, rowpos):
        """ The current row is the row that stays fixed when rows are inserted, or removed"""
        self.fixed_row = rowpos
        self.PaintRect(self.GetClientRect())

    def GetFixedRow(self):
        return first(self.displayed_rows, lambda e: e.rowpos == self.fixed_row)
        
    def GetRowCached(self, row_id):
        result = self.datamodel.Get(row_id)
        self.heights.add(row_id, result.height)
        return result

    def ReindexDisplayedRows(self, reindex_func):
        if self.fixed_row is not None:
            self.fixed_row = reindex_func(self.fixed_row)
        for d in self.displayed_rows:
            d.rowpos = reindex_func(d.rowpos)          
        self.heights.reindex(reindex_func)

    def OnInserted(self, insert_pos, reindex_func):
        self.ReindexDisplayedRows(reindex_func)      
        fixed_row = self.GetFixedRow()
        if self.fixed_row:
            self.ScrollToLayout(self.fixed_row, fixed_row.y)
        else:
            self.ScrollToLayout(self.displayed_rows[0].rowpos, self.displayed_rows[0].y)
        self.PaintRect(self.GetClientRect())
        wx.PostEvent(self, RowScrollerDisplayChanged())     
            
    def OnRemoved(self, pos, reindex_func):
        if self.fixed_row == pos:
            self.fixed_row = None 
        fixed_row = self.GetFixedRow()
        self.ReindexDisplayedRows(reindex_func)      
        if self.fixed_row:
            self.ScrollToLayout(self.fixed_row, fixed_row.y)
        else:
            self.ScrollToLayout(self.displayed_rows[0].rowpos, self.displayed_rows[0].y)
        self.PaintRect(self.GetClientRect())

    def OnModified(self, rowpos):
        disprow = first(self.displayed_rows, lambda e: e.rowpos == rowpos)
        if not disprow:
            return
        row = self.GetRowCached(rowpos)
        if row.height != disprow.height():
            fixed_row = self.GetFixedRow()
            if self.fixed_row:
                self.ScrollToLayout(self.fixed_row, fixed_row.y)
            else:
                self.ScrollToLayout(self.displayed_rows[0].rowpos, self.displayed_rows[0].y)
            self.PaintRect(self.GetClientRect())
        else:
            self.RepaintRow(rowpos)
            self.BlitToScreen(self.GetLayoutRect(rowpos))
    
    def GetLayoutRect(self, rowpos):
        disprow = first(self.displayed_rows, lambda e: e.rowpos == rowpos)
        result = wx.Rect(0, disprow.y, self.client_width, disprow.end_y) 

    def PaintRow(self, dc, row, start_y, end_y):
        dc.SetClippingRegion (wx.Rect((self.margin, start_y , self.client_width, end_y - start_y)))
        dc.Clear()
        row.Paint(dc, self.margin, start_y)
        dc.DestroyClippingRegion()

    def RepaintRow(self, rowpos):
        d = first(self.displayed_rows, lambda e: e.rowpos == rowpos)
        #rowpos, row, start_y, next_y = self.displayed_rows(rowpos)
        self.dc_back.SetClippingRegion(wx.Rect(self.margin, d.y , self.client_width, d.height()))
        self.dc_back.Clear()
        d.row.Paint(self.dc_back, self.margin, d.y)
        self.dc_back.DestroyClippingRegion()

    def BlitToScreen(self, rect):
        # TODO: Remove this..
        rect = self.GetClientRect()
        dc = wx.ClientDC(self)
        dc.Blit(rect.x, rect.y, rect.width, rect.height, self.dc_back, rect.x, rect.y)

    def PaintRect(self, rect, refresh=True):
        self.dc_back.SetClippingRegion(rect)
        self.dc_back.Clear()
        for displayed_row in self.displayed_rows:
            if displayed_row.y + displayed_row.row.height >= rect.top:
                self.PaintRow(self.dc_back, displayed_row.row, displayed_row.y, displayed_row.y + displayed_row.row.height)
            if displayed_row.y >= rect.bottom:
                break
            if self.fixed_row is not None:
                self.dc_back.SetBrush( wx.TRANSPARENT_BRUSH)
                self.dc_back.SetPen( wx.BLACK_PEN )
                fixed_row = first(self.displayed_rows, lambda e: e.rowpos == self.fixed_row)
                if fixed_row:
                    self.dc_back.DrawRectangle(1, fixed_row.y+1, self.client_width-2, fixed_row.end_y - fixed_row.y - 2)
        self.BlitToScreen(rect)
        self.dc_back.DestroyClippingRegion()

    def ScrollBackBufferRow(self, start_y, end_y, distance):
        self.dc_back.Blit(0, start_y+distance, self.client_width, end_y - start_y, self.dc_back, 0, start_y)

    def ScrollBackBuffer(self, distance):
        # do we need another image (e.g. test Blit for overlapping regions)
        self.dc_back.Blit(0, distance, self.client_width, self.inner_height, self.dc_back, 0, 0)

    def HitTest(self, x, y):
        x -= self.margin
        for displayed_row in self.displayed_rows:
            if displayed_row.y <= y <= displayed_row.end_y:
                return (displayed_row.rowpos, ) + displayed_row.row.HitTest(x, y-displayed_row.y)

    def OnSize(self, event):
        #print ("OnSize", event)
        self.client_width, self.client_height = self.GetClientSize()
        self.inner_height = self.client_height
        self.BackBuffer = wx.Bitmap(self.client_width, self.client_height)
        self.dc_back = MemoryDC()
        self.dc_back.SelectObject(self.BackBuffer)
        #self.ResetHeightEstimate()
        # Estimate Height
        max_idx = self.datamodel.GetApproximateCount()
        if max_idx < 50:
            rowsample = range(max_idx)
        else:
            rowsample = set([self.datamodel.GetApproximatePos(random.randrange(0, max_idx)) for _ in range(50)])
        for pos in rowsample:
            self.heights.add(pos, self.datamodel.Get(pos).height)

        if self.displayed_rows:
            rowpos, y = self.displayed_rows[0].rowpos, self.displayed_rows[0].y
        else:
            rowpos, y = self.datamodel.GetFirstPos(), 0
        self.ScrollToLayout(rowpos, y)
        self.PaintRect(self.GetClientRect(), refresh=True)
        event.Skip()

    def GetScrollPosition(self):
        return self.current_pos

    def GetInnerHeight(self):
        return self.inner_height
    
    def RefreshScrollBar(self):
        # idx = self.GetApproximateIndex(self.layout_rows[0][0])
        # This line was removed as it was unused. Would we need this?
        self.SetScrollbar(wx.VERTICAL, self.current_pos, self.inner_height, self.heights.estimate() * self.datamodel.GetApproximateCount(),  refresh=True)

    def Display(self, displayed_row, position):
        #print ("Displaying", displayed_row)
        self.displayed_rows.insert(position, displayed_row)

    def Hide(self, top=True):
        if top: 
            result = self.displayed_rows.popleft()
        else: 
            result = self.displayed_rows.pop()
        #print ("Hiding", result)

    def FillRemaingRows(self):
        if self.displayed_rows: 
            # Expand bottom
            displayed_row = self.displayed_rows[-1]
            y = displayed_row.y
            rowpos = self.datamodel.GetNextPos(displayed_row.rowpos)
            while y + displayed_row.row.height < self.inner_height and rowpos is not None:
                row = self.GetRowCached(rowpos)
                y += displayed_row.row.height
                displayed_row = DisplayedRow(y, y+row.height, rowpos, row) 
                self.Display(displayed_row, len(self.displayed_rows))
                rowpos = self.datamodel.GetNextPos(displayed_row.rowpos)
            # Expand top
            displayed_row = self.displayed_rows[0]
            y = displayed_row.y
            rowpos = self.datamodel.GetPrevPos(displayed_row.rowpos)
            while y > 0 and rowpos is not None:

                row = self.GetRowCached(rowpos)
                y -= row.height
                self.Display(DisplayedRow(y, y+row.height, rowpos, row), 0)
                rowpos = self.datamodel.GetPrevPos(rowpos)
                
    def ClearExtraRows(self):
        # Remove Top
        while self.displayed_rows and self.displayed_rows[0].y + self.displayed_rows[0].row.height <= 0:
            self.Hide(True)
        # Remove Bottom            
        while self.displayed_rows and self.displayed_rows[-1].y >= self.inner_height:
            self.Hide(False)
    


    def ScrollToLayout(self, rowpos, start_px):
        """  Absolute scroll rows such that the row 'rowpos' is now at 'start_px' pixels
        from the top of the window (start_px can be negative).
        """
        y = start_px
        self.displayed_rows = deque()
        if rowpos is not None:
            row = self.GetRowCached(rowpos)
            self.displayed_rows.append(DisplayedRow(y, y+row.height, rowpos, row))
        self.FillRemaingRows()          
        self.RefreshScrollBar()        

    def _ScrollNoRefresh(self, distance):
        ''' Relative Scroll distance in pixels (negative is up) '''
        if distance == 0:
            return 0
        if distance > 0:
            distance_moved = self.MoveDownBottom(distance)
            self.MoveDownTop(distance_moved)
        else:
            distance_moved = self.MoveUpTop(-distance)
            self.MoveUpBottom(distance_moved)
        distance_moved = math.copysign(distance_moved, distance)
        self.current_pos = max(min(self.current_pos + distance_moved, self.estimated_height), 0)
        return distance_moved

    def _RefreshAfterScrolling(self, distance):
        ''' Refresh after scrolling distance pixels (negative is up) '''
        if abs(distance) < self.inner_height:
            if distance > 0:
                paint_rect = wx.Rect(0, self.inner_height-distance, self.client_width, self.client_height)
            else:
                paint_rect = wx.Rect(0, 0, self.client_width, -distance)
            self.ScrollBackBuffer(-distance)
            self.ScrollWindow(0, -distance)
        else:
            paint_rect = wx.Rect(0, 0, self.client_width, self.inner_height)
        self.PaintRect(paint_rect, refresh=True)
        self.RefreshScrollBar()

    def _ScrollUntil(self, distance_increment, fct):
        ''' Relative Scroll distance_increment in pixels until fct returns True.
            Then, refresh the screen.
            This can be used for "Scroll until cursor is in view"
        '''
        distance_moved = 0
        while not fct:
            distance_moved += self._ScrollNoRefresh(distance_increment)

    def ScrollIntoViewXY(self, row_id, x, y):
        return self.ScrollIntoRectView(row_id, wx.Rect(x, y, 0, 0))

    def ScrollIntoRectView(self, row_id, rect):
        # FIXME
        print ("ScrollIntoRectView")
        first, last = self.layout_row_ids[0], self.layout_row_ids[-1]
        if row_id > last:
            #self.ScrollIntoViewXY2(row_id, rect.left, rect.bottom)
            self.ScrollToLayout(row_id, self.inner_height - 1 - rect.bottom)
            self.PaintRect(self.GetClientRect(), refresh=True)
            self.RefreshScrollBar()
            
        elif row_id < first:
            self.ScrollToLayout(row_id, -rect.top)
            self.PaintRect(self.GetClientRect(), refresh=True)
            self.RefreshScrollBar()
            #self.ScrollIntoViewXY2(row_id, rect.left, rect.top)
        elif row_id == last:
            missing = max(rect.bottom - self.PixelsVisibleLastRow(), 0)
            distance_moved = self.Scroll(missing)
        elif row_id == first:
            missing = max(self.PixelsHiddenFirstRow()-rect.top, 0)
            distance_moved = self.Scroll(-missing)

    def _ScrollRows(self, distance):
        for displayed_row in self.displayed_rows:
            displayed_row.y -= distance
            displayed_row.end_y -= distance

    def Scroll(self, distance, bounded_scolling=True):
        if not self.displayed_rows:
            return
        self._ScrollRows(distance)
        self.FillRemaingRows()
        scrolled_pixels = distance
        # Now we might have scrolled too far
        if bounded_scolling:
            if distance < 0:
                if self.displayed_rows[0].y > 0:
                    dist = self.displayed_rows[0].y
                    self._ScrollRows(dist)
                    scrolled_pixels += dist
            elif distance > 0:
                if self.displayed_rows[-1].y < self.inner_height - self.displayed_rows[-1].row.height:
                    dist = self.displayed_rows[-1].y - (self.inner_height - self.displayed_rows[-1].row.height) 
                    self._ScrollRows(dist)
                    scrolled_pixels += dist
            self.FillRemaingRows()
        self.ClearExtraRows()
        self.current_pos += scrolled_pixels
        paint_rect = wx.Rect(0, 0, self.client_width, self.inner_height)
        self.PaintRect(paint_rect, refresh=True)
        self.RefreshScrollBar()       
        wx.PostEvent(self, RowScrollerScrolledEvent())     
            
    def ScrollTo(self, pos):
        '''Absolute scroll pos in pixels'''
        # pos varies between 0 and self.estimated_height - self.inner_height
        if abs(pos - self.current_pos) < 1000:
            # Avoid flickering, when scrolling small distances by doing a relative scroll
            return self.Scroll(pos - self.current_pos)
        else:
            estimated_row_height = self.heights.estimate()
            rowpos = self.datamodel.GetApproximatePos(pos // int(estimated_row_height))
            hidden_first_row = pos % int(estimated_row_height)
            self.ScrollToLayout(rowpos, hidden_first_row)
        self.PaintRect(self.GetClientRect(), refresh=True)
        self.current_pos = pos
        self.RefreshScrollBar()
        wx.PostEvent(self, RowScrollerScrolledEvent())     

    def OnScroll(self, event):
        event_type = event.GetEventType()
        if event_type == wx.EVT_SCROLLWIN_PAGEDOWN.typeId:
            pos = event.GetPosition()
            self.Scroll(self.inner_height)
        elif event_type == wx.EVT_SCROLLWIN_PAGEUP.typeId:
            self.Scroll(-self.inner_height)
        elif event_type == wx.EVT_SCROLLWIN_THUMBTRACK.typeId:
            pos = event.GetPosition()
            self.ScrollTo(pos)
        elif event_type == wx.EVT_SCROLLWIN_THUMBRELEASE.typeId:
            pos = event.GetPosition()
            self.ScrollTo(pos)

    def OnMouseWheel(self, event):
        rotation = event.GetWheelRotation()
        delta = event.GetWheelDelta()
        self.Scroll(-self.line_size * (rotation / delta))

    def __OnChar(self, event):
        key_code = event.GetKeyCode()
        if key_code == WXK_PAGEDOWN:
            self.Scroll(self.inner_height)
        elif key_code == WXK_PAGEUP:
            self.Scroll(-self.inner_height)
        elif key_code == WXK_UP:
            self.Scroll(-self.line_size)
        elif key_code == WXK_DOWN:
            self.Scroll(self.line_size)
        event.Skip()


class ColorRow():
    def __init__(self, row_id=None, width=None, height=None, color=None):
        self.row_id = row_id
        self.width = width or random.randrange(100, 400)
        self.height = height or random.randrange(20, 100)
        self.color = color or wx.Colour(red=random.randrange(20, 70)*3, green=random.randrange(3, 7)*40, blue=0)

    def __repr__(self):
        return (f"ColorRow<{self.row_id}, {self.height}>")
    
    def Paint(self, dc, x, y):
        dc.SetBrush(wx.Brush(self.color, wx.SOLID))
        dc.SetPen( wx.TRANSPARENT_PEN )
        dc.DrawRectangle(0, y, self.width, self.height)
        dc.DrawText(str(self.row_id), x, y)
        dc.DrawText(str(self.height), x+100, y)

    def HitTest(self, x, y):
        return (x, y)

    def clone(self, idx):
        return ColorRow(idx, self.width, self.height, self.color)


class ColorRowModel():
    """ rowpos, must support __add__ (+1, -1)
    """
    def __init__(self):
        self.count = 50
        self.real_count = 10000
        random.seed(3)
        
        self.rows = [ColorRow(idx) for idx in range(self.real_count)]
        self.MODIFIED = Event()
        self.INSERTED = Event()
        self.DELETED = Event()
    
    def Insert(self, pos, row):
        self.rows.insert(pos, row)
        self.count += 1
        self.INSERTED.fire(pos, lambda p: p+1 if p >=pos else p )

    def Remove(self, pos):
        self.rows = self.rows[:pos] + self.rows[pos+1:]
        self.count -= 1
        self.DELETED.fire(pos, lambda p: p-1 if p > pos else p )

    def Modify(self, pos):
        if pos %2 == 0:
            self.rows[pos].height -= 5
        else:
            self.rows[pos].height += 5
        self.MODIFIED.fire(pos)

    def Get(self, pos):
        if pos >= self.count:
            raise Exception("not found")
        return self.rows[pos%self.real_count]

    def GetFirstPos(self):
        return 0

    def GetNextPos(self, pos):
        if pos == self.count -1:
            return None
        return pos+1

    def GetPrevPos(self, pos):
        if pos == 0:
            return None
        return pos-1

    def GetLastPos(self):
        return self.count - 1

    def GetApproximatePos(self, index):
        """ index: value between 0 and GetApproximateCount()  """
        return max(min(index, self.count-1), 0)

    def GetApproximateIndex(self, rowpos):
        return rowpos

    def GetApproximateCount(self):
        return self.count
    
    


if __name__ == '__main__':

    class TestFrame(wx.Frame):
        def __init__(self, parent=None):
            super(TestFrame, self).__init__(parent, size=(500, 600), pos=(100, 50))
            hbox = wx.BoxSizer(wx.HORIZONTAL)
            self.model = ColorRowModel()
            self.ctrl =  RowScroller(self.model, self)
            self.ctrl.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
            self.ctrl.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
            self.ctrl.Bind(wx.EVT_CHAR, self.OnChar)
            self.ctrl.Bind(EVT_ROWSCROLLER_SCROLLED, self.OnScrolled)
            self.ctrl.Bind(EVT_ROWSCROLLER_DISPLAY_CHANGED, self.OnScrolled)
            
            vbox = wx.BoxSizer(wx.VERTICAL)
            vbox.Add(wx.StaticText(self, label="Estimated Height"))
            self.txt1 = wx.TextCtrl(self, 0)
            #self.txt1.Disable()
            vbox.Add(self.txt1, 0, wx.EXPAND|wx.ALL)
            vbox.Add(wx.StaticText(self, label="Scroll Position"))
            self.txt2 = wx.TextCtrl(self, 0)
            #self.txt2.Disable()
            vbox.Add(self.txt2, 0, wx.EXPAND|wx.ALL)
            vbox.Add(wx.StaticText(self, label="Inner Height"))
            self.txt3 = wx.TextCtrl(self, 0)
            #self.txt3.Disable()
            vbox.Add(self.txt3, 0, wx.EXPAND|wx.ALL)
            vbox.Add(wx.StaticText(self, label="Based On"))
            self.txt4 = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(10, 300))
            #self.txt4.Disable()
            vbox.Add(self.txt4, 0, wx.EXPAND|wx.ALL)
                        
            hbox.Add(self.ctrl, 2, wx.EXPAND|wx.ALL)
            hbox.Add(vbox, 1, wx.EXPAND|wx.ALL)
            
            
            self.SetSizer(hbox)
            self.Layout()
            self.i = 10

        def OnScrolled(self, event):
            self.txt1.SetLabel(str(self.ctrl.heights.estimate() * self.ctrl.datamodel.GetApproximateCount()))
            self.txt2.SetLabel(str(self.ctrl.GetScrollPosition()))
            self.txt3.SetLabel(str(self.ctrl.GetInnerHeight()))
            self.txt4.SetLabel(str(sorted(self.ctrl.heights.row_heights.keys())))

        def OnLeftDown(self, event):
            x, y = event.GetPosition()
            rowpos, x, y = self.ctrl.HitTest(x, y)
            b = min(random.randrange(2, 8)*40, 255)
            g = min(random.randrange(2, 8)*40, 255)
            color = wx.Colour(red=0, green=g, blue=b)
            row = ColorRow(self.i, color=color)
            self.ctrl.datamodel.Insert(rowpos, row)
            self.i += 1

        def OnRightDown(self, event):
            x, y = event.GetPosition()
            result = self.ctrl.HitTest(x, y)
            if result:
                rowpos, x, y = result
                b = min(random.randrange(2, 8)*40, 255)
                g = min(random.randrange(2, 8)*40, 255)
                '''color = wx.Colour(red=0, green=g, blue=b)
                row = self.ctrl.GetRowCached(rowpos)'''
                self.ctrl.datamodel.Remove(rowpos)
                self.i += 1

        def OnChar(self, event):
            key_code = event.GetKeyCode()
            if key_code == ord("f"):
                x, y = event.GetPosition()
                rowpos, x, y = self.ctrl.HitTest(x, y)
                self.ctrl.SetFixedRow(rowpos)
            if key_code == ord("i"):
                self.OnLeftDown(event)
            if key_code == ord("d"):
                self.OnRightDown(event)
            if key_code == ord("m"):
                x, y = event.GetPosition()
                result = self.ctrl.HitTest(x, y)
                if result:
                    rowpos, x, y = result
                    self.model.Modify(rowpos)
                    self.i += 1
               
            event.Skip()


    app = wx.App()
    frame = TestFrame()
    frame.Show()
    app.SetTopWindow(frame)
    app.MainLoop()

