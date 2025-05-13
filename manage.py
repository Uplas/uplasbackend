import os
import sys

# Add the 'backend' directory to the Python path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BACKEND_DIR)

import django
from django.core.management import execute_from_command_line
