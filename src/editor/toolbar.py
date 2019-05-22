from editor import icons
import wx
from editor.fontpicker import FontPickerComboBox

class RichTextToolbar(wx.ToolBar):
    def __init__(self, parent):
        super().__init__(parent)
        tsize = (24,24)
        self.SetToolBitmapSize(tsize)
        #img = wx.Image("png\\bold.png").ConvertToBitmap()
        self.AddTool(10, "Bold", icons.bold.GetBitmap(), wx.NullBitmap, wx.ITEM_CHECK, "Bold", "Long help for 'Bold'", None)
        #self.Bind(wx.EVT_TOOL, self.OnToolClick, id=10)
        #self.Bind(wx.EVT_TOOL_RCLICKED, self.OnToolRClick, id=10)
        self.AddTool(20, "Italic", icons.italic.GetBitmap(), wx.NullBitmap, wx.ITEM_CHECK, "Italic", "Long help for 'Italic'", None)
        self.AddSeparator()
        self.AddTool(30, "Align Left", icons.left_align.GetBitmap(), wx.NullBitmap, wx.ITEM_CHECK, "Align Left", "Long help for 'Align Left'", None)
        self.AddTool(40, "Align Center", icons.center_align.GetBitmap(), wx.NullBitmap, wx.ITEM_CHECK, "Align Center", "Long help for 'Center'", None)
        self.AddTool(40, "Align Right", icons.right_align.GetBitmap(), wx.NullBitmap, wx.ITEM_CHECK, "Align Right", "Long help for 'Align Right'", None)
        self.AddTool(40, "Justify", icons.justify.GetBitmap(), wx.NullBitmap, wx.ITEM_CHECK, "Justify", "Long help for 'Justify'", None)

        self.AddTool(40, "Underline", icons.underline.GetBitmap(), wx.NullBitmap, wx.ITEM_CHECK, "Underline", "Long help for 'Justify'", None)
        self.AddSeparator()

        cbID = wx.NewId()
        cbID2 = wx.NewId()
        #wx.ComboBox( self, cbID, "", choices=[""], size=(150,-1), style=wx.CB_DROPDOWN )
        self.AddControl(wx.ComboBox( self, cbID, "", choices=[""], size=(150,-1), style=wx.CB_DROPDOWN ))
        #self.AddControl(FontPickerComboBox(self, size=(150,-1)))
        self.AddControl(wx.ComboBox( self, cbID2, "", choices=[""], size=(50,-1), style=wx.CB_DROPDOWN ))

        self.AddStretchableSpace()

        self.Realize()

