from django.contrib import admin

from accounts.models import Account


@admin.register(Account)
class AuthorAdmin(admin.ModelAdmin):
    pass
