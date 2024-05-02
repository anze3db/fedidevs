from django.contrib import admin

from stats.models import Daily


# Register your models here.
@admin.register(Daily)
class AuthorAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "total_accounts",
        "python_accounts",
        "javascript_accounts",
        "rust_accounts",
        "ruby_accounts",
        "golang_accounts",
        "java_accounts",
        "kotlin_accounts",
        "scala_accounts",
        "swift_accounts",
        "csharp_accounts",
        "fsharp_accounts",
        "dotnet_accounts",
        "cpp_accounts",
        "linux_accounts",
        "haskell_accounts",
        "ocaml_accounts",
        "nix_accounts",
        "opensource_accounts",
        "php_accounts",
        "css_accounts",
    )
