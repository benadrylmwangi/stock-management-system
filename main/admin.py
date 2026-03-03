from django.contrib import admin
from .models import Customer,Stock,Commodity,Sales,Debtors
# Register your models here.
admin.site.register(Customer)
admin.site.register(Stock)
admin.site.register(Commodity)
admin.site.register(Sales)
admin.site.register(Debtors)