import machine
import time

# Display resolution (from original driver)
EPD_WIDTH = 122
EPD_HEIGHT = 250

class FrameBuffer:
    def __init__(self, width=EPD_WIDTH, height=EPD_HEIGHT, bg=0xff):
        self.width = width
        self.height = height
        # Calculate how many bytes are needed per row (rounding up)
        self.line_bytes = (width + 7) // 8
        self.buffer_size = self.line_bytes * height
        # Initialize the buffer; use 0x00 for black, or 0xff for white
        self.buffer = bytearray([bg] * self.buffer_size)
    
    def clear(self, color=0xff):
        """Clear the framebuffer by filling it with the given color (0x00 for black, 0xff for white)."""
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

    def draw_line(self, x0, y0, x1, y1, color, thickness=1):
        """
        Draw a line from (x0, y0) to (x1, y1) using Bresenham's algorithm.
        The 'color' parameter follows the same convention as in draw_pixel.
        The optional 'thickness' parameter (default 1) controls the line thickness.
        
        For thickness > 1, the algorithm draws lines above and below current one
        """
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy  # error value

        if thickness == 1:
            # Standard Bresenham's algorithm
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
        else:
            x0t = x0 - int(thickness/2)
            x1t = x1 - int(thickness/2)
            for i in range(thickness):
                self.draw_line(x0t, y0, x1t, y1, color)
                x0t+=1
                x1t+=1


class EPD:
    def __init__(self, spi, cs_pin, dc_pin, rst_pin, busy_pin):
        # Set up hardware pins
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
        self.send_command(0x12)  # SWRESET
        self.ReadBusy()
        self.send_command(0x18)  # Read built-in temperature sensor
        self.send_command(0x80)
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

    def display(self, image):
        # image should be a buffer (list or bytearray) of the correct size
        self.send_command(0x24)
        self.send_data2(image)
        self.TurnOnDisplay()

    def display_fast(self, image):
        self.send_command(0x24)
        self.send_data2(image)
        self.TurnOnDisplay_Fast()

    def displayPartial(self, image):
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
        self.send_command(0x24)  # WRITE_RAM
        self.send_data2(image)
        self.TurnOnDisplayPart()

    def displayPartBaseImage(self, image):
        self.send_command(0x24)
        self.send_data2(image)
        self.send_command(0x26)
        self.send_data2(image)
        self.TurnOnDisplay()

    def Clear(self, color=0xFF):
        # Calculate line width (in bytes)
        if self.width % 8 == 0:
            linewidth = self.width // 8
        else:
            linewidth = (self.width // 8) + 1
        self.send_command(0x24)
        self.send_data2([color] * (self.height * linewidth))
        self.TurnOnDisplay()

    def sleep(self):
        self.send_command(0x10)  # Enter deep sleep
        self.send_data(0x01)
        self.delay_ms(2000)
        # Optionally deinitialize SPI or set pins to a low-power state
        # self.spi.deinit()

# Example usage:
if __name__ == '__main__':
    # Initialize SPI
    spi = machine.SPI(1, baudrate=2000000, polarity=0, phase=0, sck=machine.Pin(10), mosi=machine.Pin(11))
    # Create an EPD instance and initialize it
    epd = EPD(spi, cs_pin=9, dc_pin=8, rst_pin=12, busy_pin=13)
    epd.init()
    # Clear the display
    epd.Clear(0xff)
    
    # Display a line
    image_buffer = FrameBuffer()
    image_buffer.draw_line(100, 100, 50, 200, 0x00, 60)
    epd.display(image_buffer.buffer)

    # Put the display to sleep when done
    epd.sleep()


