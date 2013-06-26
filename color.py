import webcolors
from PIL import Image
from colormath.color_objects import RGBColor

# Kelly's list of 22 colours of maximum contrast
# Taken from http://eleanormaclure.files.wordpress.com/2011/03/colour-coding.pdf
# Thanks to http://stackoverflow.com/questions/470690/how-to-automatically-generate-n-distinct-colors

kelly_colours = {
    #"hex": ["name", Lab, Order]
    "#817066": ["medium_gray", None, 0],
    "#000000": ["black", None, 1],
    "#232C16": ["dark_olive-green", None, 2],
    "#593315": ["deep_yellowish-brown", None, 3],
    "#007D34": ["vivid_green", None, 4],
    "#7F180D": ["strong_reddish-brown", None, 5],
    "#93AA00": ["vivid_yellowish-green", None, 6],
    "#C10020": ["vivid_red", None, 7],
    "#53377A": ["strong_violet", None, 8],
    "#F13A13": ["reddish-orange", None, 9],
    "#803E75": ["strong_purple", None, 10],
    "#B32851": ["strong_purplish-red", None, 11],
    "#00538A": ["strong_blue", None, 12],
    "#F6768E": ["strong_purplish-pink", None, 13],
    "#A6BDD7": ["very_light_blue", None, 14],
    "#FF7A5C": ["strong_yellowish-pink", None, 15],
    "#FF8E00": ["vivid_orange_yellow", None, 16],
    "#FF6800": ["vivid_orange", None, 17],
    "#FFB300": ["vivid_yellow", None, 18],
    "#CEA262": ["grayish_yellow", None, 19],
    "#F4C800": ["vivid_greenish-yellow", None, 20],
    "#FFFFFF": ["white", None, 21],
}

# Store the lab values for each colour
for key, bits in kelly_colours.items():
    rgb = webcolors.hex_to_rgb(key)
    bits[1] = RGBColor(*rgb).convert_to("lab")


def most_frequent_colours(image, top=3):
    """Find the most common colours in a numpy array.
    Quantization done with PIL. I tried the k-means method in scipy
    but it was slower and not necessarily better"""
    # image = image.resize((100, 100))
    result = image.convert('P',
                           palette=Image.ADAPTIVE,
                           colors=top)
    result.putalpha(0)
    colors = [x[1] for x in result.getcolors(image.size[0] * image.size[1])]
    return colors


def closest_colour(requested_colour):
    """Find the colour in kelly_colours that is closest to this one.
    requested_colour is an RGB tuple."""
    rlab = RGBColor(*requested_colour).convert_to("lab")
    better_colours = {}
    for key, bits in kelly_colours.items():
        lab_diff = rlab.delta_e(bits[1])
        better_colours[lab_diff] = key
    return better_colours[min(better_colours.keys())]


def get_colour_name(requested_colour):
    return closest_colour(requested_colour)
