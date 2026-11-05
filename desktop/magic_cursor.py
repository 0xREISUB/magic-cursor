#!/usr/bin/env python3
"""Magic Cursor başlatıcısı — asıl kod magiccursor/ paketinde.

Kullanım: magic_cursor.py [toggle | quit | help]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from magiccursor.main import main  # noqa: E402

if __name__ == '__main__':
    main()
