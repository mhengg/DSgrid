import numpy as np
import pandas as pds
import webcolors

def multi_index(df, cols):
    result = df.copy()
    if len(cols) == 1:
        result.index = result[cols[0]]
    else:
        result.index = pds.MultiIndex.from_tuples(list(zip(*[result[col].tolist() for col in cols])),
                                                  names = cols)
    for col in cols:
        del result[col]
    return result  

def lighten_color(hex_color,fraction_to_white):
    rgb_color = np.array(webcolors.hex_to_rgb(hex_color))
    white = np.array([255,255,255])
    direction = white - rgb_color
    result = [int(round(x)) for x in list(rgb_color + direction * fraction_to_white)]
    return webcolors.rgb_to_hex(tuple(result))
    
def palette(hex_color,n,max_fraction=0.75):
    result = []; step = max_fraction / float(n)
    for frac in [i * step for i in range(n)]:
        result.append(lighten_color(hex_color,frac))
    assert len(result) == n
    return result
