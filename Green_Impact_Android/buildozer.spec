[app]

title = Green Impact
package.name = greenimpact
package.domain = org.gamefication

version = 0.9.6

icon.filename = assets/app_icon.png

source.dir = .
source.include_exts = py,png,jpg,json,txt,md,ico,icns
source.exclude_dirs = tests,bin,dist,__pycache__,.venv,venv

entrypoint = main.py
requirements = python3,kivy==2.3.1,websockets==12.0

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE
android.api = 36
android.minapi = 26
android.ndk = 28c
android.archs = arm64-v8a

p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
