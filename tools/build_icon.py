"""Convert the approved artwork into PNG-backed Windows ICO sizes using Qt."""
from pathlib import Path
import struct
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage


def build(source, destination):
    image = QImage(str(source))
    if image.isNull(): raise ValueError('Icon artwork could not be loaded')
    frames = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        scaled = image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        buffer = QBuffer(); buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not scaled.save(buffer, 'PNG'): raise ValueError('PNG conversion failed')
        frames.append((size, bytes(buffer.data())))
    header = struct.pack('<HHH', 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    directory = []
    for size, data in frames:
        dimension = 0 if size == 256 else size
        directory.append(struct.pack('<BBBBHHII', dimension, dimension, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    Path(destination).write_bytes(header + b''.join(directory) + b''.join(data for _, data in frames))


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    build(root / 'assets' / 'aetherftp.png', root / 'assets' / 'aetherftp.ico')
