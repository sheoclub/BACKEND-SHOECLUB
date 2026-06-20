# This file contains the WSGI configuration required to serve up your
# web application at http://sheoclub.pythonanywhere.com/
# It works by setting the variable 'application' to a WSGI handler of some
# description.

import os
import sys

# add your project directory to the sys.path
project_home = '/home/sheoclub/BACKEND-SHOECLUB'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# set environment variable to tell django where your settings.py is
os.environ['DJANGO_SETTINGS_MODULE'] = 'shoeclub.settings'

# --- Environment Variables (from .env file) ---
os.environ['DEBUG'] = 'False'
os.environ['SECRET_KEY'] = 'm2^-h+d#h=kr7g@v(c7@id+t7x@^z@(o*(91)0ukjf_v(og@uk'
os.environ['ALLOWED_HOSTS'] = '.pythonanywhere.com,localhost,127.0.0.1'
os.environ['DATABASE_URL'] = 'postgresql://postgres.arzviualzyawvvkyfden:Ak47sheoclub@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres?sslmode=require'
os.environ['TIME_ZONE'] = 'Asia/Karachi'
os.environ['SECURE_SSL_REDIRECT'] = 'True'
os.environ['CORS_ALLOWED_ORIGINS'] = ''
# ------------------------------------------------

# serve django via WSGI
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
