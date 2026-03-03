from django.db import models

# Create your models here.
class Customer(models.Model):
    business_name=models.CharField(max_length=200,unique=True, null=False)
    email=models.EmailField(max_length=200,unique=True,null=False)
    phone_number=models.CharField(max_length=10,unique=True,null=False,default='0700000000')
    password=models.CharField(max_length=200,null=False)
    confirm_password=models.CharField(max_length=200,null=False,default='password')
    timestamp=models.DateTimeField(auto_now_add=True)

    def __str__(self):        
        return f"{self.business_name} - {self.timestamp}"
    
class Commodity(models.Model):
    name=models.CharField(max_length=200,unique=True)
    buying_price=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    number_of_commodity=models.IntegerField(default=0)
    amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    timestamp=models.DateTimeField(auto_now_add=True)


    def __str__(self):        
        return f"{self.name} - {self.timestamp} - {self.number_of_commodity} - {self.buying_price} - {self.selling_price} - {self.amount} - {self.total_amount}"
class Stock(models.Model):
    # each stock row is tied to both a customer and a commodity
    # when the commodity is deleted we cascade; if the customer is removed
    # all their stock goes with them.
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="stocks")
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name="stocks")

    # most of the data is redundant with the commodity but stored here
    # so that the customer can have a per‑commodity copy (price, amount etc.)
    name_commodity = models.CharField(max_length=200)
    number_of_commodity = models.IntegerField(default=0)
    buying_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "commodity"],
                name="unique_stock_per_customer_commodity",
            )
        ]

    def save(self, *args, **kwargs):
        # whenever a stock row is saved, copy the current commodity values
        if self.commodity:
            self.name_commodity = self.commodity.name
            self.buying_price = self.commodity.buying_price
            self.amount = self.commodity.amount
            self.total_amount = self.commodity.total_amount
            # number_of_commodity left to be managed by whatever view/form creates stocks
        super().save(*args, **kwargs)

    def __str__(self):        
        return f"{self.name_commodity} - {self.customer.business_name} - {self.timestamp}- {self.number_of_commodity} - {self.buying_price} - {self.amount} - {self.total_amount}"
    
class Sales(models.Model):
    commodity = models.ForeignKey(Commodity,on_delete=models.PROTECT,related_name="sales")

    name=models.CharField(max_length=200)
    buying_price=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    number_of_commodity=models.IntegerField(default=0)
    amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    timestamp=models.DateTimeField(auto_now_add=True)


    def __str__(self):        
        return f"{self.name} - {self.timestamp} - {self.number_of_commodity} - {self.buying_price} - {self.selling_price} - {self.amount} - {self.total_amount}"
class Debtors(models.Model):
    name=models.CharField(max_length=200)
    sale = models.OneToOneField(Sales,on_delete=models.CASCADE,related_name="debt")
    number_of_commodity=models.IntegerField(default=0)
    amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    timestamp=models.DateTimeField(auto_now_add=True)


    def __str__(self):        
        return f"{self.name} - {self.timestamp} - {self.number_of_commodity} - {self.amount} - {self.total_amount}"