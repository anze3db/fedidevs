# import multiprocessing

pidfile = "gunicorn.pid"
proc_name = "fedidevs"
bind = "unix:fedidevs.sock"
workers = 4  # multiprocessing.cpu_count() + 1
threads = 4  # multiprocessing.cpu_count() * 2
# Access log - records incoming HTTP requests
# accesslog = "/var/log/gunicorn-fedidevs.access.log"
# Error log - records Gunicorn server goings-on
# errorlog = "/var/log/gunicorn-fedidevs.error.log"
# Whether to send Django output to the error log
# capture_output = True
# How verbose the Gunicorn error logs should be
# loglevel = "info"
