import wx
from wx import MemoryDC, WXK_PAGEDOWN, WXK_PAGEUP, WXK_UP, WXK_DOWN
from _collections import deque
import random
import time
from enum import Enum
import math
from editor.event import Event


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

def CorrectInsertPos(pos, insert_position):
    if insert_position <= pos:
        return pos + 1
    return pos

def CorrectRemovePos(pos, removed_position):
    if removed_position < pos:
        return pos - 1
    return pos



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
        
        self.displayed_rows = deque()
        
        self.pixels_hidden_first_row = 0
        self.pixels_hidden_last_row = 0
        self.client_height = 0
        self.layout_row_ids = deque() # deque of row_ids currently layout
        self.layout_rows = {} # row_ids => row
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
        
    def ResetHeightEstimate(self):
        max_idx = self.datamodel.GetApproximateCount()
        self.estimated_height = None
        self.height_of_rows_seen = {}
        self.rows_seen = set()
        self.sum_heigth_of_rows_seen = 0
        random_pos = [self.datamodel.GetApproximatePos(random.randrange(0, max_idx)) for _ in range(50)]
        for pos in random_pos:
            row = self.datamodel.Get(pos)
            self.AddHeighForEstimate(pos, row.height)

    def SetFixedRow(self, index):
        """ The current row is the row that stays fixed when rows are inserted, or removed"""
        self.fixed_row = index

    def InsertAfter(self, pos, row):
        pass

    def GetFixedPostion(self):
        if self.fixed_row is not None:
            return self.fixed_row
        return self.layout_row_ids[0]

    def StartLayout(self, rowpos, hidden_first_row=0, hidden_last_row=0):
        self.pixels_hidden_first_row = hidden_first_row
        self.pixels_hidden_last_row = hidden_last_row
        self.layout_row_ids = deque([rowpos])
        self.GetRowCached(rowpos)
        
    def IterateRowLayout(self):
        current_y = -self.PixelsHiddenFirstRow()
        for rowpos in self.layout_row_ids:
            row = self.GetRowCached(rowpos)
            next_y = current_y + row.height
            yield (rowpos, row, current_y, next_y)
            current_y += row.height
        if current_y - self.pixels_hidden_last_row > self.inner_height:
            raise Exception("err")

    def GetLayoutY(self, pos):
        # We don't store current_y/next_y currently. We could maybe but we
        # would have to recompute them when scrolling
        for rowpos, row, current_y, next_y in self.IterateRowLayout():
            if rowpos == pos:
                return current_y

    def ClearRowCache(self, row_id):
        if row_id in self.layout_rows:
            row = self.layout_rows[row_id]
            del self.layout_rows[row_id]
            self.RemoveHeighForEstimate(row_id, row.height)

    def GetRowCached(self, row_id):
        if row_id in self.layout_rows:
            return self.layout_rows[row_id]
        self.layout_rows[row_id] = result = self.datamodel.Get(row_id)
        return result

    def GetRowCachedNoRefresh(self, row_id):
        if row_id in self.layout_rows:
            return self.layout_rows[row_id]
        self.layout_rows[row_id] = result = self.Get(row_id)
        return result

    def IncrementRowIds(self, start, increment):
        """ Batch Increment/Decrement row_ids when inserting and deleting rows"""
        keys = set(k for k,v in self.layout_rows.items() if k >= start)
        layout_with_new_keys = {k+increment:self.layout_rows[k] for k in keys}
        for k in keys:
            del self.layout_rows[k]
        self.layout_rows.update(layout_with_new_keys)


    def IterateLayoutRows(self, start, end_included):
        for rowpos, row, current_y, next_y in self.IterateRowLayout():
            if rowpos < start:
                continue
            if rowpos > end_included:
                break
            yield rowpos, row

    def GetLayoutParams(self, pos):
        for rowpos, row, current_y, next_y in self.IterateRowLayout():
            if rowpos == pos:
                return rowpos, row, current_y, next_y

    def GetLayoutHeight(self, pos):
        for rowpos, row, current_y, next_y in self.IterateRowLayout():
            if rowpos == pos:
                return next_y - current_y

    def GetLayoutRect(self, pos):
        for rowpos, row, current_y, next_y in self.IterateRowLayout():
            if rowpos == pos:
                return wx.Rect(self.margin, current_y, self.client_width-self.margin*2, next_y)

    def OnInserted(self, pos):
        # pos: index name before insertion happened, GetRow(pos) will return the new inserted item
        self.IncrementRowIds(pos, 1)
        row = self.GetRowCached(pos)
        fixed_row = self.GetFixedPostion()
        fixed_row_y = self.GetLayoutY(fixed_row) or 0
        fixed_row = CorrectInsertPos(fixed_row, pos)
        if self.fixed_row is not None:
            self.fixed_row = CorrectInsertPos(self.fixed_row, pos)
        # FixME: self.current_pos  depends on Fixed_row
        self.current_pos += row.height
        self.estimated_height += row.height
        self.ScrollToLayout(fixed_row, fixed_row_y)
        # fix this
        self.PaintRect(self.GetClientRect())

    def IsVisibleRow(self, pos):
        return (pos in self.layout_row_ids)
    
    def OnRemoved(self, pos):
        oldrow = self.layout_rows.get(pos)
        self.ClearRowCache(pos)
        #print (self.layout_rows)
        self.IncrementRowIds(pos, -1)
        #print (self.layout_rows)
        if not self.IsVisibleRow(pos):
            return
        fixed_row = self.GetFixedPostion()
        fixed_row_y = self.GetLayoutY(fixed_row) or 0
        fixed_row = CorrectRemovePos(fixed_row, pos)
        if self.fixed_row is not None:
            self.fixed_row = CorrectRemovePos(self.fixed_row, pos)
        self.current_pos -= oldrow.height
        self.estimated_height -= oldrow.height
        self.ScrollToLayout(fixed_row, fixed_row_y)
        # fix this
        self.PaintRect(self.GetClientRect())

    def OnModified(self, rowpos):
        oldrow = self.layout_rows.get(rowpos)
        self.ClearRowCache(rowpos)
        if not self.IsVisibleRow(rowpos):
            return
        row = self.GetRowCached(rowpos)
        if row.height != oldrow.height:
            fixed_row = self.GetFixedPostion()
            fixed_row_y = self.GetLayoutY(fixed_row) or 0
            self.ScrollToLayout(fixed_row, fixed_row_y)
            self.PaintRect(self.GetClientRect())
        else:
            self.RepaintRow(rowpos)
            self.BlitToScreen(self.GetLayoutRect(rowpos))

    def PaintRow(self, dc, row, start_y, end_y):
        dc.SetClippingRegion (wx.Rect((self.margin, start_y , self.client_width, end_y - start_y)))
        dc.Clear()
        row.Paint(dc, self.margin, start_y)
        dc.DestroyClippingRegion()

    def RepaintRow(self, rowpos):
        rowpos, row, start_y, next_y = self.GetLayoutParams(rowpos)
        self.dc_back.SetClippingRegion(wx.Rect(self.margin, start_y , self.client_width, next_y - start_y))
        self.dc_back.Clear()
        row.Paint(self.dc_back, self.margin, start_y)
        self.dc_back.DestroyClippingRegion()

    def BlitToScreen(self, rect):
        # TODO: Remove this..
        rect = self.GetClientRect()
        dc = wx.ClientDC(self)
        dc.Blit(rect.x, rect.y, rect.width, rect.height, self.dc_back, rect.x, rect.y)

    def PaintRect(self, rect, refresh=True):
        self.dc_back.SetClippingRegion(rect)
        self.dc_back.Clear()
        for _rowpos, row, current_y, next_y in self.IterateRowLayout():
            if current_y + row.height >= rect.top:
                self.PaintRow(self.dc_back, row, current_y, next_y)
            if current_y >= rect.bottom:
                break
        if refresh:
            self.BlitToScreen(rect)
        self.dc_back.DestroyClippingRegion()

    def ScrollBackBufferRow(self, start_y, end_y, distance):
        self.dc_back.Blit(0, start_y+distance, self.client_width, end_y - start_y, self.dc_back, 0, start_y)

    def ScrollBackBuffer(self, distance):
        # do we need another image (e.g. test Blit for overlapping regions)
        self.dc_back.Blit(0, distance, self.client_width, self.inner_height, self.dc_back, 0, 0)

    def HitTest(self, x, y):
        x -= self.margin
        for rowpos, row, start_y, end_y in self.IterateRowLayout():
            if start_y <= y <= end_y:
                return (rowpos, ) + row.HitTest(x, y-start_y)

    def AddRowBottom(self):
        assert self.PixelsHiddenLastRow() == 0
        rowpos = self.layout_row_ids[-1]
        nextpos = self.datamodel.GetNextPos(rowpos)
        if nextpos is not None:
            nextrow = self.GetRowCached(nextpos)
            self.AddHeighForEstimate(nextpos, nextrow.height)
            self.layout_row_ids.append(nextpos)
            self.layout_rows[nextpos] = nextrow
            self.pixels_hidden_last_row = nextrow.height
            return rowpos

    def AddRowTop(self):
        assert self.PixelsHiddenFirstRow() == 0
        rowpos = self.layout_row_ids[0]
        prevpos = self.datamodel.GetPrevPos(rowpos)
        if prevpos is not None:
            prevrow = self.GetRowCached(prevpos)
            self.AddHeighForEstimate(prevpos, prevrow.height)
            self.layout_row_ids.appendleft(prevpos)
            self.layout_rows[prevpos] = prevrow
            self.pixels_hidden_first_row = prevrow.height
            return rowpos

    def RemoveRowTop(self):
        assert self.PixelsVisibleFirstRow() == 0
        assert len(self.layout_row_ids)
        self.pixels_hidden_first_row = 0
        rowid = self.layout_row_ids.popleft()
        del self.layout_rows[rowid]

    def RemoveRowBottom(self):
        assert self.PixelsVisibleLastRow() == 0
        assert len(self.layout_row_ids)
        self.pixels_hidden_last_row = 0
        rowid = self.layout_row_ids.pop()
        del self.layout_rows[rowid]

    def PixelsHiddenFirstRow(self):
        return (self.pixels_hidden_first_row)

    def PixelsVisibleFirstRow(self):
        row = self.GetRowCached(self.layout_row_ids[0])
        return (row.height - self.pixels_hidden_first_row)

    def PixelsHiddenLastRow(self):
        return self.pixels_hidden_last_row

    def PixelsVisibleLastRow(self):
        row = self.GetRowCached(self.layout_row_ids[-1])
        return (row.height - self.pixels_hidden_last_row)

    def HideFirstRow(self, pixels):
        self.pixels_hidden_first_row += pixels

    def ShowFirstRow(self, pixels):
        self.pixels_hidden_first_row -= pixels

    def HideLastRow(self, pixels):
        self.pixels_hidden_last_row += pixels

    def ShowLastRow(self, pixels):
        self.pixels_hidden_last_row -= pixels

    def MoveDownBottom(self, distance):
        remaining = distance
        while remaining:
            n = self.PixelsHiddenLastRow()
            if n:
                value = min(n, remaining)
                self.ShowLastRow(value)
                remaining -= value
            else:
                if self.AddRowBottom() is None:
                    # no next element
                    break
        return distance - remaining

    def MoveDownTop(self, distance):
        remaining = distance
        while remaining:
            n = self.PixelsVisibleFirstRow()
            if n:
                value = min(n, remaining)
                self.HideFirstRow(value)
                remaining -= value
            else:
                self.RemoveRowTop()
        return distance - remaining

    def MoveUpTop(self, distance):
        remaining = distance
        while remaining:
            n = self.PixelsHiddenFirstRow()
            if n:
                value = min(n, remaining)
                self.ShowFirstRow(value)
                remaining -= value
            else:
                if self.AddRowTop() is None:
                    # no previous element
                    break
        return distance - remaining

    def MoveUpBottom(self, distance):
        remaining = distance
        while remaining:
            n = self.PixelsVisibleLastRow()
            if n:
                value = min(n, remaining)
                self.HideLastRow(value)
                remaining -= value
            else:
                self.RemoveRowBottom()
        return distance - remaining

    def OnSize(self, event):
        self.client_width, self.client_height = self.GetClientSize()
        self.inner_height = self.client_height
        self.BackBuffer = wx.Bitmap(self.client_width, self.client_height)
        self.dc_back = MemoryDC()
        self.dc_back.SelectObject(self.BackBuffer)
        self.ResetHeightEstimate()
        self.layout_rows = {} #Clear all cached rows
        pos = self.layout_row_ids and self.layout_row_ids[0] or self.datamodel.GetFirstPos()
        if pos is not None:
            self.ScrollToLayout(pos, -self.pixels_hidden_first_row)
        self.PaintRect(self.GetClientRect(), refresh=True)
        event.Skip()

    def EstimateTotalHeight(self):
        self.estimated_row_height = self.Estimate_RowHeight()
        self.estimated_height = self.estimated_row_height*self.datamodel.GetApproximateCount()

    def AddHeighForEstimate(self, rowpos, height):
        if rowpos not in self.rows_seen:
            self.height_of_rows_seen[rowpos] = height
            self.rows_seen.add(rowpos)
            self.sum_heigth_of_rows_seen += height

    def RemoveHeighForEstimate(self, rowpos, height):
        if rowpos in self.rows_seen:
            self.rows_seen.remove(rowpos)
            self.sum_heigth_of_rows_seen -= height


    def Estimate_RowHeight(self):
        return self.sum_heigth_of_rows_seen / len(self.rows_seen)

    def RefreshScrollBar(self):
        # idx = self.GetApproximateIndex(self.layout_rows[0][0])
        # This line was removed as it was unused. Would we need this?
        self.EstimateTotalHeight()
        self.SetScrollbar(wx.VERTICAL, self.current_pos, self.inner_height, self.estimated_height, refresh=True)

    def ScrollToLayout(self, rowpos, start_px):
        """  Absolute scroll rows such that the row 'rowpos' is now at 'start_px' pixels
        from the top of the window (start_px can be negative).
        
        1/ Refactor this to remove MoveDownBottom/MoveDownTop etc..
        """
        self.StartLayout(rowpos)
        row = self.layout_rows[self.layout_row_ids[0]]
        if start_px <= 0:
            self.MoveDownBottom(self.inner_height-start_px-row.height)
            self.MoveDownTop(-start_px)
        elif 0 <= start_px <= self.inner_height:
            self.MoveUpTop(start_px)
            self.MoveDownBottom(self.inner_height-start_px-row.height)
        elif start_px > self.inner_height:
            self.MoveUpTop(start_px)
            self.MoveUpBottom(start_px-self.inner_height+row.height)
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

    def Scroll(self, distance):
        ''' Relative Scroll distance in pixels (negative is up) '''
        distance_moved = self._ScrollNoRefresh(distance)
        if not distance_moved:
            return
        self._RefreshAfterScrolling(distance_moved)

    def ScrollTo(self, pos):
        '''Absolute scroll pos in pixels'''
        # pos varies between 0 and self.estimated_height - self.inner_height
        if abs(pos - self.current_pos) < 1000:
            # Avoid flickering, when scrolling small distances by doing a relative scroll
            return self.Scroll(pos - self.current_pos)
        if pos + self.inner_height >= self.estimated_height:
            # bottom
            last = self.datamodel.GetLastPos()
            row = self.GetRowCached(last)
            self.ScrollToLayout(last, self.inner_height - row.height)
        else:
            estimated_row_height = self.Estimate_RowHeight()
            rowpos = self.datamodel.GetApproximatePos(pos // int(estimated_row_height))
            hidden_first_row = pos % int(estimated_row_height)
            self.ScrollToLayout(rowpos, hidden_first_row)
        self.PaintRect(self.GetClientRect(), refresh=True)
        self.current_pos = pos
        self.RefreshScrollBar()

    def OnScroll(self, event):
        event_type = event.GetEventType()
        if event_type == wx.EVT_SCROLLWIN_PAGEDOWN.typeId:
            pos = event.GetPosition()
            self.Scroll(self.inner_height)
        elif event_type == wx.EVT_SCROLLWIN_PAGEUP.typeId:
            self.Scroll(-self.inner_height)
        elif event_type == wx.EVT_SCROLLWIN_THUMBTRACK.typeId:
            pos = event.GetPosition()
            print (pos, self.current_pos, self.estimated_height)
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
        self.count = 500
        self.real_count = 10000
        self.rows = [ColorRow(idx) for idx in range(self.real_count)]
        self.MODIFIED = Event()
        self.INSERTED = Event()
        self.DELETED = Event()
    

    def Insert(self, pos, row):
        self.rows.insert(pos, row)
        self.count += 1
        self.INSERTED.fire(pos)

    def Remove(self, pos):
        self.rows = self.rows[:pos] + self.rows[pos+1:]
        self.count -= 1
        self.DELETED.fire(pos)

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
            vbox = wx.BoxSizer(wx.VERTICAL)
            self.ctrl =  RowScroller(ColorRowModel(), self)
            self.ctrl.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
            self.ctrl.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
            self.ctrl.Bind(wx.EVT_CHAR, self.OnChar)
            vbox.Add(self.ctrl, 1, wx.EXPAND|wx.ALL)
            self.SetSizer(vbox)
            self.Layout()
            self.i = 10

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
            rowpos, x, y = self.ctrl.HitTest(x, y)
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
                row, x, y = self.ctrl.HitTest(x, y)
                self.ctrl.SetFixedRow(row)
            if key_code == ord("i"):
                self.OnLeftDown(event)
            if key_code == ord("d"):
                self.OnRightDown(event)
            event.Skip()


    app = wx.App()
    frame = TestFrame()
    frame.Show()
    app.SetTopWindow(frame)
    app.MainLoop()

