import machine
import time
import math
import json

# Display resolution (from original driver)
EPD_WIDTH = 122
EPD_HEIGHT = 250

def scale_polygon(polygon, scale):
    if scale == 1:
        return polygon
    return [[int(round(x * scale)), int(round(y * scale))] for x, y in polygon]

def move_polygon(polygon, delta_x, delta_y):
    return [[int(x + delta_x), int(y + delta_y)] for x, y in polygon]

def rotate_polygon(polygon, angle):
    """Rotate the polygon by a given angle in degrees clockwise."""
    if angle == 0:
        return polygon
    rad = math.radians(angle)
    cos_theta = math.cos(rad)
    sin_theta = math.sin(rad)
    
    rotated = []
    for x, y in polygon:
        # Apply the rotation matrix:
        x_new = x * cos_theta - y * sin_theta
        y_new = x * sin_theta + y * cos_theta
        rotated.append([int(round(x_new)), int(round(y_new))])
    
    return rotated

class FrameBuffer:
    def __init__(self, width=EPD_WIDTH, height=EPD_HEIGHT, bg=0xff):
        self.width = width
        self.height = height
        # Calculate how many bytes are needed per row (rounding up)
        self.line_bytes = (width + 7) // 8
        self.buffer_size = self.line_bytes * height
        self.buffer = bytearray([bg] * self.buffer_size)

    
    def clear(self, color=0xff):
        for i in range(self.buffer_size):
            self.buffer[i] = color

    def draw_pixel(self, x, y, color):
        """
        Set the pixel at (x,y) to the given color.
        The color parameter is treated as a boolean value:
          - any non-zero value sets the pixel 'on'
          - 0 clears the pixel.
        """
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return  # Ignore pixels out of bounds
        
        # Determine which byte and bit correspond to (x,y)
        byte_index = y * self.line_bytes + (x >> 3)
        bit = 0x80 >> (x & 7)  # highest order bit is on the left
        
        if color:
            self.buffer[byte_index] |= bit
        else:
            self.buffer[byte_index] &= ~bit

    def draw_line(self, x0, y0, x1, y1, color):
        """
        Draw a line from (x0, y0) to (x1, y1) using Bresenham's algorithm.
        The 'color' parameter follows the same convention as in draw_pixel.
        """
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy  # error value

        # Bresenham's algorithm
        while True:
            self.draw_pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy
                    
    def draw_polygon(self, point_list, color, fill=False):
        # makes an outline by drawing lines (end of first line is start of a second one)
        old_point = point_list[-1]
        for point in point_list:
            self.draw_line(*old_point, *point, color)
            old_point = point
            
            if fill:
                # Compute the bounding box for the polygon
                ys = [p[1] for p in point_list]
                min_y = max(min(ys), 0)
                max_y = min(max(ys), self.height - 1)

                # For each scanline between min_y and max_y:
                for y in range(min_y, max_y + 1):
                    intersections = []
                    n = len(point_list)
                    for i in range(n):
                        p1 = point_list[i]
                        p2 = point_list[(i + 1) % n]
                        # Skip horizontal edges to avoid duplicates
                        if p1[1] == p2[1]:
                            continue
                        # Check if the scanline crosses the edge
                        if (y >= min(p1[1], p2[1])) and (y < max(p1[1], p2[1])):
                            # Linear interpolation to find intersection x-coordinate
                            x_int = p1[0] + (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1])
                            intersections.append(x_int)
                    intersections.sort()
                    # Fill between pairs of intersections
                    for i in range(0, len(intersections), 2):
                        if i + 1 < len(intersections):
                            x_start = int(math.ceil(intersections[i]))
                            x_end = int(math.floor(intersections[i + 1]))
                            # Clip to display boundaries
                            x_start = max(x_start, 0)
                            x_end = min(x_end, self.width - 1)
                            for x in range(x_start, x_end + 1):
                                self.draw_pixel(x, y, color)
                                
    def draw_text(self, x, y, text, size, color, fill=False, rotate=0):
        tx = x
        ty = y
        
        if rotate:
            rad = math.radians(rotate)
            advance_dx = 7 * size * math.cos(rad)
            advance_dy = 7 * size * math.sin(rad)
            del rad
        else:
            advance_dx = 7 * size
            advance_dy = 0
        
        with open('characters.json', 'r') as file:
            data = json.load(file)
        for c in text:
            if c == " ":
                tx += advance_dx
                ty += advance_dy
                continue
            char_polygon = data[c]
            self.draw_polygon(move_polygon(rotate_polygon(scale_polygon(char_polygon, size), rotate), tx, ty), color, fill)
            tx += advance_dx
            ty += advance_dy


class EPD:
    def __init__(self, spi, cs_pin, dc_pin, rst_pin, busy_pin):
        # Set up hardware pins
        self.fbuf = FrameBuffer()
        self.spi = spi
        self.cs = machine.Pin(cs_pin, machine.Pin.OUT)
        self.dc = machine.Pin(dc_pin, machine.Pin.OUT)
        self.rst = machine.Pin(rst_pin, machine.Pin.OUT)
        self.busy = machine.Pin(busy_pin, machine.Pin.IN)
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT
        self.cs.value(1)

    def delay_ms(self, ms):
        time.sleep_ms(ms)

    def spi_writebyte(self, data):
        self.spi.write(bytearray(data))

    def spi_writebyte2(self, data):
        # data is expected to be an iterable of byte values
        self.spi.write(bytearray(data))

    def reset(self):
        self.rst.value(1)
        self.delay_ms(20)
        self.rst.value(0)
        self.delay_ms(2)
        self.rst.value(1)
        self.delay_ms(20)

    def send_command(self, command):
        self.dc.value(0)
        self.cs.value(0)
        self.spi_writebyte([command])
        self.cs.value(1)

    def send_data(self, data):
        self.dc.value(1)
        self.cs.value(0)
        self.spi_writebyte([data])
        self.cs.value(1)

    def send_data2(self, data):
        self.dc.value(1)
        self.cs.value(0)
        self.spi_writebyte2(data)
        self.cs.value(1)

    def ReadBusy(self):
        # Wait until the busy pin is low (0 means idle)
        while self.busy.value() == 1:
            self.delay_ms(10)

    def TurnOnDisplay(self):
        self.send_command(0x22)  # Display Update Control
        self.send_data(0xf7)
        self.send_command(0x20)  # Activate Display Update Sequence
        self.ReadBusy()

    def TurnOnDisplay_Fast(self):
        self.send_command(0x22)
        self.send_data(0xC7)  # fast: 0x0c, quality: 0x0f, 0xcf
        self.send_command(0x20)
        self.ReadBusy()

    def TurnOnDisplayPart(self):
        self.send_command(0x22)
        self.send_data(0xff)
        self.send_command(0x20)
        self.ReadBusy()

    def SetWindow(self, x_start, y_start, x_end, y_end):
        self.send_command(0x44)  # SET_RAM_X_ADDRESS_START_END_POSITION
        self.send_data((x_start >> 3) & 0xFF)
        self.send_data((x_end >> 3) & 0xFF)
        self.send_command(0x45)  # SET_RAM_Y_ADDRESS_START_END_POSITION
        self.send_data(y_start & 0xFF)
        self.send_data((y_start >> 8) & 0xFF)
        self.send_data(y_end & 0xFF)
        self.send_data((y_end >> 8) & 0xFF)

    def SetCursor(self, x, y):
        self.send_command(0x4E)  # SET_RAM_X_ADDRESS_COUNTER
        self.send_data(x & 0xFF)
        self.send_command(0x4F)  # SET_RAM_Y_ADDRESS_COUNTER
        self.send_data(y & 0xFF)
        self.send_data((y >> 8) & 0xFF)

    def init(self):
        self.reset()
        self.ReadBusy()
        self.send_command(0x12)  # SWRESET
        self.ReadBusy()
        self.send_command(0x01)  # Driver output control
        self.send_data(0xf9)
        self.send_data(0x00)
        self.send_data(0x00)
        self.send_command(0x11)  # Data entry mode
        self.send_data(0x03)
        self.SetWindow(0, 0, self.width - 1, self.height - 1)
        self.SetCursor(0, 0)
        self.send_command(0x3c)
        self.send_data(0x05)
        self.send_command(0x21)  # Display update control
        self.send_data(0x00)
        self.send_data(0x80)
        self.send_command(0x18)
        self.send_data(0x80)
        self.ReadBusy()
        return 0

    def init_fast(self):
        self.reset()
        self.ReadBusy()
        self.send_command(0x12)  # SWRESET
        self.ReadBusy()
        self.send_command(0x18)  # Read built-in temperature sensor
        self.send_data(0x80)
        self.send_command(0x11)  # Data entry mode
        self.send_data(0x03)
        self.SetWindow(0, 0, self.width - 1, self.height - 1)
        self.SetCursor(0, 0)
        self.send_command(0x22)  # Load temperature value
        self.send_data(0xB1)
        self.send_command(0x20)
        self.ReadBusy()
        self.send_command(0x1A)  # Write to temperature register
        self.send_data(0x64)
        self.send_data(0x00)
        self.send_command(0x22)  # Load temperature value
        self.send_data(0x91)
        self.send_command(0x20)
        self.ReadBusy()
        return 0

    def display(self):
        # image should be a buffer (list or bytearray) of the correct size
        self.send_command(0x24)
        self.send_data2(self.fbuf.buffer)
        self.TurnOnDisplay()

    def display_fast(self):
        self.send_command(0x24)
        self.send_data2(self.fbuf.buffer)
        self.TurnOnDisplay_Fast()
        
    def init_part(self):
        self.rst.value(0)
        self.delay_ms(1)
        self.rst.value(1)
        self.send_command(0x3C)  # Border Waveform
        self.send_data(0x80)
        self.send_command(0x01)  # Driver output control
        self.send_data(0xF9)
        self.send_data(0x00)
        self.send_data(0x00)
        self.send_command(0x11)  # Data entry mode
        self.send_data(0x03)
        self.SetWindow(0, 0, self.width - 1, self.height - 1)
        self.SetCursor(0, 0)


    def displayPartial(self):
        self.SetWindow(0, 0, self.width - 1, self.height - 1)
        self.SetCursor(0, 0)
        self.send_command(0x24)  # WRITE_RAM
        self.send_data2(self.fbuf.buffer)
        self.TurnOnDisplayPart()

    def displayPartBaseImage(self):
        self.send_command(0x24)
        self.send_data2(self.fbuf.buffer)
        self.send_command(0x26)
        self.send_data2(self.fbuf.buffer)
        self.TurnOnDisplay()

    def Clear(self, color=0xFF):
        self.fbuf.clear(color)
        # Calculate line width (in bytes)
        if self.width % 8 == 0:
            linewidth = self.width // 8
        else:
            linewidth = (self.width // 8) + 1
        self.send_command(0x24)
        self.send_data2([color] * (self.height * linewidth))
        self.TurnOnDisplay()
        
    def ClearPart(self, color=0xFF):
        self.fbuf.clear(color)
        # Calculate line width (in bytes)
        if self.width % 8 == 0:
            linewidth = self.width // 8
        else:
            linewidth = (self.width // 8) + 1
        self.send_command(0x24)
        self.send_data2([color] * (self.height * linewidth))
        self.TurnOnDisplayPart()

    def sleep(self):
        self.send_command(0x10)  # Enter deep sleep
        self.send_data(0x01)
        self.delay_ms(200)
        # Optionally deinitialize SPI or set pins to a low-power state
        self.rst.value(0)

# Example usage
if __name__ == '__main__':
    # Initialize SPI and EDP instance
    # Adjust pin numbers for your wiring
    spi = machine.SPI(1, baudrate=2000000, polarity=0, phase=0, sck=machine.Pin(10), mosi=machine.Pin(11))
    epd = EPD(spi, cs_pin=9, dc_pin=8, rst_pin=12, busy_pin=13)
    epd.init()
    # Clear the display
    epd.Clear(0xff)
    # Display 3 triangles
    epd.fbuf.draw_polygon([[0, 0], [25, 200], [0, 225]], 0x00, True)
    epd.fbuf.draw_polygon([[0, 0], [50, 175], [30, 195]], 0x00, False)
    epd.fbuf.draw_polygon([[0, 0], [75, 125], [55, 170]], 0x00, True)
    # Display a line
    epd.fbuf.draw_line(78, 0, 78, 300, 0x00)
    
    # Fast display
    epd.display_fast()
    
    # Display text
    epd.fbuf.draw_text(x=110, y=5, text="rusofobia", size=4, color=0x00, fill=True, rotate=90)

    # Partial display
    epd.init_part()
    epd.displayPartial()
    
    # Partial clear
    time.sleep_ms(2000)
    epd.ClearPart(0xff)

    # Put the display to sleep when done
    epd.sleep()
