from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import zlib

from app.schemas.trend_assessment import TrendInputV1, TrendMetricSample


@dataclass(frozen=True)
class TrendChartArtifact:
    metric_name: str
    path: Path


def render_trend_charts(trend_input: TrendInputV1, output_dir: Path) -> list[TrendChartArtifact]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[TrendChartArtifact] = []
    configs = [
        ("cpu", trend_input.metrics.cpu.samples, (70.0, 85.0), (53, 119, 241)),
        ("memory", trend_input.metrics.memory.samples, (75.0, 85.0), (5, 150, 105)),
        ("disk", trend_input.metrics.disk.samples, (80.0, 85.0, 90.0), (196, 76, 29)),
    ]
    for metric_name, samples, thresholds, color in configs:
        if len(samples) < 2:
            continue
        target_path = output_dir / f"{metric_name}_trend.png"
        _render_line_chart(samples, target_path=target_path, thresholds=thresholds, line_color=color)
        artifacts.append(TrendChartArtifact(metric_name=metric_name, path=target_path))
    return artifacts


def _render_line_chart(
    samples: list[TrendMetricSample],
    *,
    target_path: Path,
    thresholds: tuple[float, ...],
    line_color: tuple[int, int, int],
) -> None:
    width = 800
    height = 480
    canvas = _Canvas(width=width, height=height, background=(255, 255, 255))
    plot_left = 72
    plot_right = width - 40
    plot_top = 36
    plot_bottom = height - 56
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    y_max = max(100.0, max(sample.value for sample in samples) + 10.0, max(thresholds) + 5.0)
    y_min = 0.0

    canvas.fill_rect(plot_left, plot_top, plot_width, plot_height, (250, 252, 255))
    for index in range(6):
        y = plot_bottom - int(plot_height * index / 5)
        canvas.draw_line(plot_left, y, plot_right, y, (228, 233, 240), 1)
    for threshold in thresholds:
        y = _value_to_y(threshold, y_min=y_min, y_max=y_max, plot_top=plot_top, plot_bottom=plot_bottom)
        canvas.draw_line(plot_left, y, plot_right, y, (232, 110, 92), 1)

    canvas.draw_rect(plot_left, plot_top, plot_width, plot_height, (70, 85, 110), 2)

    points: list[tuple[int, int]] = []
    denominator = max(1, len(samples) - 1)
    for index, sample in enumerate(samples):
        x = plot_left + int(plot_width * index / denominator)
        y = _value_to_y(sample.value, y_min=y_min, y_max=y_max, plot_top=plot_top, plot_bottom=plot_bottom)
        points.append((x, y))
    for previous, current in zip(points, points[1:]):
        canvas.draw_line(previous[0], previous[1], current[0], current[1], line_color, 3)
    for x, y in points:
        canvas.fill_rect(x - 3, y - 3, 7, 7, line_color)

    _write_png(target_path, width=width, height=height, rgb_bytes=canvas.to_bytes())


def _value_to_y(value: float, *, y_min: float, y_max: float, plot_top: int, plot_bottom: int) -> int:
    ratio = 0.0 if y_max <= y_min else (value - y_min) / (y_max - y_min)
    ratio = min(max(ratio, 0.0), 1.0)
    return plot_bottom - int((plot_bottom - plot_top) * ratio)


class _Canvas:
    def __init__(self, *, width: int, height: int, background: tuple[int, int, int]) -> None:
        self.width = width
        self.height = height
        self._pixels = bytearray(background * width * height)

    def set_pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        index = (y * self.width + x) * 3
        self._pixels[index : index + 3] = bytes(color)

    def fill_rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
        for yi in range(y, y + height):
            for xi in range(x, x + width):
                self.set_pixel(xi, yi, color)

    def draw_rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int], thickness: int) -> None:
        for offset in range(thickness):
            self.draw_line(x, y + offset, x + width, y + offset, color, 1)
            self.draw_line(x, y + height - offset, x + width, y + height - offset, color, 1)
            self.draw_line(x + offset, y, x + offset, y + height, color, 1)
            self.draw_line(x + width - offset, y, x + width - offset, y + height, color, 1)

    def draw_line(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        color: tuple[int, int, int],
        thickness: int,
    ) -> None:
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        error = dx + dy
        while True:
            for offset_x in range(-(thickness // 2), thickness // 2 + 1):
                for offset_y in range(-(thickness // 2), thickness // 2 + 1):
                    self.set_pixel(x1 + offset_x, y1 + offset_y, color)
            if x1 == x2 and y1 == y2:
                break
            error2 = 2 * error
            if error2 >= dy:
                error += dy
                x1 += sx
            if error2 <= dx:
                error += dx
                y1 += sy

    def to_bytes(self) -> bytes:
        return bytes(self._pixels)


def _write_png(target_path: Path, *, width: int, height: int, rgb_bytes: bytes) -> None:
    raw_rows = []
    stride = width * 3
    for row_index in range(height):
        row = rgb_bytes[row_index * stride : (row_index + 1) * stride]
        raw_rows.append(b"\x00" + row)
    compressed = zlib.compress(b"".join(raw_rows), level=9)
    png_bytes = b"\x89PNG\r\n\x1a\n"
    png_bytes += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0
    ))
    png_bytes += _png_chunk(b"IDAT", compressed)
    png_bytes += _png_chunk(b"IEND", b"")
    target_path.write_bytes(png_bytes)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )
