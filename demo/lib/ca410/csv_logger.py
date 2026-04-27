import csv
import os


class CA410CSVLogger:
    def __init__(self, filepath):
        self.filepath = filepath
        self.header_written = os.path.exists(filepath)

    def write_row(self, data: dict):
        if not data:
            return

        file_exists = os.path.exists(self.filepath)

        with open(self.filepath, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data.keys())

            # 第一次写入：写表头
            if not file_exists:
                writer.writeheader()

            writer.writerow(data)