import wx


class Caret(wx.EvtHandler):
    def __init__(self): 
        super().__init__()
        self.paragraph_layout = None
        self.position = None
        self.blink_flag = True
        self.caret_timer = wx.Timer(self)
        self.visible = False
        self.Bind(wx.EVT_TIMER, self.OnCaretTimer, self.caret_timer)
        
    def OnCaretTimer(self, event):
        self.Blink()
            
    def Show(self, visible=True):
        self.visible = visible
        self.CaretReset()

    def Blink(self):
        if self.paragraph_layout:
            self.paragraph_layout.ShowCaret(self.blink_flag and self.visible, self.position.richttext, self.position.offset)
            self.blink_flag = not self.blink_flag
            self.layout.Modified(self.paragraph)

    def SetCaret(self, paragraph, richttext, offset):
        if self.paragraph_layout is not None:
            self.paragraph_layout.ShowCaret(False, self.richttext, self.offset)
            self.layout.Modified(self.paragraph)
        self.paragraph_layout = self.layout.GetLayoutRow(paragraph)
        self.paragraph = paragraph
        self.richttext = richttext
        self.offset = offset
        self.CaretReset()
        
    def CaretReset(self):
        self.caret_timer.Stop()
        self.blink_flag = True
        # Common to all carets for MSW compatibility
        self.caret_timer.Start(500) 
        self.Blink()
        self.layout.Modified(self.paragraph)
    