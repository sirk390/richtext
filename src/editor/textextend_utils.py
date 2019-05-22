from editor.docmodel import TextStyle
import wx

Measure_cache = {}
Dc = None
Fonts = {}
FontDCs = {}

def GetFontCached(style):
    # TODO:: use FontList.FindOrCreateFont
    global Fonts
    if style not in Fonts:
        Fonts[style] = style.GetWxFont() if style else TextStyle().GetWxFont()
    return Fonts[style]


def GetFontDCCached(style):
    global FontDCs
    font = GetFontCached(style)
    if style not in FontDCs:
        FontDCs[style] = dc = wx.MemoryDC()
        dc.SetFont(font)
    return FontDCs[style]
    

def GetTextExtentCached(word, style):
    global Dc, Measure_cache
    if (word, style) in Measure_cache:
        return Measure_cache[(word, style)]
    font = GetFontCached(style)
    if Dc is None:
        Dc = wx.MemoryDC()
    w, h, descent, externalLeading= Dc.GetFullTextExtent(word, font)
    #size = wx.Size(w,h)
    Measure_cache[(word, style)] = (w, h) 
    return w, h


def GetPartialTextExtents(text, style):
    dc = GetFontDCCached(style)
    return dc.GetPartialTextExtents(text)
