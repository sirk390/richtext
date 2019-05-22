from editor.richtext import CustomRichTextControl
import wx
from editor.toolbar import RichTextToolbar
from wx._richtext import RichTextCtrl
from editor.util import clone_multiply_list
from editor.docmodel import Paragraph, RichText, Image, RichTextDocument,\
    TextStyle, FontStyle, FontWeight


if __name__ == '__main__':
    
    class TestFrame(wx.Frame):
        def __init__(self, parent=None):
            super(TestFrame, self).__init__(parent, size=(800,600), pos=(50, 50))
            vbox = wx.BoxSizer(wx.VERTICAL)
            document = RichTextDocument(clone_multiply_list(Paragraph(RichText("hello hueuizeeuih ezhu zeiuhezu+ no word wrap, font sizes, bold, unde"*10)) * 1 +
                               [Paragraph(RichText("Hello", style=TextStyle(point_size=10)), RichText("World", style=TextStyle(point_size=70))),
                               Paragraph(Image(open("carpic.jpg", "rb").read())),
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
                rtc.WriteImage(wx.Image(open("carpic.jpg", "rb")))
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

