from django.contrib import admin
from .models import *

# Register your models here.

admin.site.register(Room)
admin.site.register(Message)
admin.site.register(BlockedUser)
admin.site.register(UserReport)