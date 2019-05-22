import wx
from wx._adv import OwnerDrawnComboBox
from wx import MemoryDC
from threading import Thread, Lock


class FontPickerComboBox(OwnerDrawnComboBox):
    
    def __init__(self, parent, size=wx.DefaultSize):
        super().__init__(parent, size=size, style=wx.CB_READONLY)
        self.font_list = []
        self.bitmaps = {}
        self.bitmaps_selected = {}
        self.sizes = {}
        self.thread = Thread(target=self.load_fonts)
        self.thread.start()
    
    def load_fonts(self):
        e = wx.FontEnumerator()
        e.OnFacename = self.OnFacename
        e.EnumerateFacenames()
        wx.CallAfter(self.join_thread)

    def join_thread(self):
        self.thread.join()
  
    def OnFacename(self, facename):
        idx = len(self.font_list)
        self.font_list.append(facename)
        w, h = self.GetTextExtentCached(idx)
        self.bitmaps[idx] = wx.Bitmap(w, h)
        dc = MemoryDC()
        dc.SelectObject(self.bitmaps[idx])
        dc.Clear()
        font = self.MakeFont(facename=facename)
        dc.SetFont(font)
        dc.DrawText(facename, 0, 0)
        wx.CallAfter(self.Append, facename, idx)
        return True
    
    def MakeFont(self, facename):
        return wx.TheFontList.FindOrCreateFont(point_size=12, family=wx.DEFAULT, style=wx.NORMAL, weight=wx.NORMAL, facename=facename)

    def OnDrawItem(self, dc, rect, item, flags):
        idx = self.GetClientData(item)
        dc_img = MemoryDC()
        dc_img.SelectObject(self.bitmaps[idx])
        w, h = self.bitmaps[idx].GetWidth(), self.bitmaps[idx].GetHeight()
        dc.Blit(rect.left, rect.top, w, h, dc_img, 0, 0, logicalFunc=wx.AND)

    def GetTextExtentCached(self, idx):
        if idx in self.sizes:
            return self.sizes[idx]
        facename = self.font_list[idx]
        font = self.MakeFont(facename=facename)
        dc = wx.MemoryDC()
        dc.SetFont(font)
        w, h = dc.GetTextExtent(facename)
        self.sizes[idx] = (w, h)
        return (w, h)
            
    def OnMeasureItem(self, item):
        return self.bitmaps[item].GetHeight()

    def OnMeasureItemWidth(self, item):
        return self.bitmaps[item].GetWidth()


if __name__ == '__main__':
    class TestFrame(wx.Frame):
        def __init__(self, parent=None):
            super(TestFrame, self).__init__(parent, size=(300, 300))
            vbox = wx.BoxSizer(wx.VERTICAL)
            ctrl =  FontPickerComboBox(self)
            vbox.Add(ctrl, 0, wx.EXPAND|wx.ALL)
            self.SetSizer(vbox)
            self.Layout()

    app = wx.App()
    frame = TestFrame()
    frame.Show()
    app.SetTopWindow(frame)
    app.MainLoop()


