from django import template

register = template.Library()

@register.filter
def format_currency(value):
    try:
        value = float(value)
        return "{:,.0f}".format(value)  # e.g., 1000000 -> 1,000,000
    except (ValueError, TypeError):
        return value