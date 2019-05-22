from editor.textextend_utils import GetPartialTextExtents, GetTextExtentCached


def parse_text(text):
    # return the next wrapping position
    current = []
    for c in text:
        if c == " ":
            current.append(c)
            yield "".join(current)
            current = []
        elif len(current) > 30:
            yield "".join(current)
            current = []
        else:
            current.append(c)
    if current:
        yield "".join(current)

def iterate_wrap_positions(text):
    word_len = 0
    for i, c in enumerate(text):
        if c == " ":
            yield i
            word_len = 0
        elif word_len > 30:
            yield i
            word_len = 0
        else:
            word_len += 1

def next_wrap_position(text, start_pos=0):
    word_len = 0
    pos = start_pos 
    wrap = False
    while pos < len(text) and not wrap:
        c = text[pos]
        if not c.isalnum():
            wrap = True
        elif word_len > 30:
            wrap = True
        else:
            word_len += 1
        pos+=1
    return pos

def wrap_next(text, text_extend_list, start_pos, max_width):
    start_width = text_extend_list[start_pos]
    next_pos = prev_pos = next_wrap_position(text, start_pos)
    while next_pos < len(text) and text_extend_list[next_pos] - start_width < max_width:
        prev_pos = next_pos
        next_pos = next_wrap_position(text, next_pos)
    if next_pos == len(text) and text_extend_list[next_pos] - start_width < max_width:
        return next_pos
    return (prev_pos)

def wrap_text(text, style, max_width, first_width=None):
    text_extends = [0] + GetPartialTextExtents(text, style)
    pos, prev_pos = 0, 0
    wrap_width = first_width or max_width
    while pos < len(text):
        next_pos = wrap_next(text, text_extends, pos, wrap_width)
        wrap_width = max_width
        yield(text[pos:next_pos])
        pos = next_pos


if __name__ == '__main__':
    import wx
    app = wx.App()
    for text in wrap_text("font sizes, bold, undehello hueuizeeuih ezhu zeiuhezu+ no word wrap, ", None, 407, 407):
        width, height = GetTextExtentCached(text, None)
        print (text, width, height)


