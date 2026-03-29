from decimal import Decimal
from datetime import timedelta

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Commodity,
    Customer,
    DebtorLedger,
    Debtors,
    Expense,
    Payment,
    ReturnEntry,
    Sales,
    Stock,
)


class SalesViewTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            business_name="Test Shop",
            email="owner@example.com",
            phone_number="0700000001",
            password="hashed-password",
            confirm_password="hashed-password",
        )
        session = self.client.session
        session["customer_id"] = self.customer.id
        session["customer_business_name"] = self.customer.business_name
        session.save()

    def test_missing_stock_shows_unavailable_message(self):
        response = self.client.post(
            reverse("sales"),
            {
                "customer_name": "Alice",
                "name": "Sugar",
                "number_of_commodity": 2,
                "selling_price": "150.00",
                "amount": "300.00",
                "payment_type": Sales.PaymentType.CASH,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("sales"))
        self.assertEqual(Sales.objects.count(), 0)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Product is currently unavailable in stock.", messages)

    def test_insufficient_stock_shows_error_message(self):
        commodity = Commodity.objects.create(
            customer=self.customer,
            name="Sugar",
            buying_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            number_of_commodity=3,
            amount=Decimal("100.00"),
            total_amount=Decimal("300.00"),
        )
        Stock.objects.filter(customer=self.customer, commodity=commodity).update(
            number_of_commodity=3
        )

        response = self.client.post(
            reverse("sales"),
            {
                "customer_name": "Alice",
                "name": "Sugar",
                "number_of_commodity": 5,
                "selling_price": "150.00",
                "amount": "750.00",
                "payment_type": Sales.PaymentType.CASH,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("sales"))
        self.assertEqual(Sales.objects.count(), 0)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Not enough stock available.", messages)

    def test_successful_sale_reduces_stock_and_creates_sale(self):
        commodity = Commodity.objects.create(
            customer=self.customer,
            name="Sugar",
            buying_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            number_of_commodity=10,
            amount=Decimal("100.00"),
            total_amount=Decimal("1000.00"),
        )
        Stock.objects.filter(customer=self.customer, commodity=commodity).update(
            number_of_commodity=10
        )

        response = self.client.post(
            reverse("sales"),
            {
                "customer_name": "Alice",
                "name": "Sugar",
                "number_of_commodity": 4,
                "selling_price": "150.00",
                "amount": "600.00",
                "payment_type": Sales.PaymentType.CASH,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("sales"))
        self.assertEqual(Sales.objects.count(), 1)

        commodity.refresh_from_db()
        stock_item = Stock.objects.get(customer=self.customer, commodity=commodity)
        self.assertEqual(commodity.number_of_commodity, 6)
        self.assertEqual(stock_item.number_of_commodity, 6)

        sale = Sales.objects.get()
        self.assertEqual(sale.commodity, commodity)
        self.assertEqual(sale.name, "Sugar")
        self.assertEqual(sale.number_of_commodity, 4)
        self.assertEqual(sale.total_amount, Decimal("600.00"))
        self.assertEqual(sale.payment_type, Sales.PaymentType.CASH)
        self.assertFalse(Debtors.objects.exists())

    def test_credit_sale_requires_customer_name(self):
        commodity = Commodity.objects.create(
            customer=self.customer,
            name="Sugar",
            buying_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            number_of_commodity=10,
            amount=Decimal("100.00"),
            total_amount=Decimal("1000.00"),
        )
        Stock.objects.filter(customer=self.customer, commodity=commodity).update(
            number_of_commodity=10
        )

        response = self.client.post(
            reverse("sales"),
            {
                "customer_name": "",
                "name": "Sugar",
                "number_of_commodity": 2,
                "selling_price": "150.00",
                "amount": "300.00",
                "payment_type": Sales.PaymentType.CREDIT,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer name is required for credit sales.")
        self.assertEqual(Sales.objects.count(), 0)
        self.assertEqual(Debtors.objects.count(), 0)

    def test_credit_sale_creates_debtor_record(self):
        commodity = Commodity.objects.create(
            customer=self.customer,
            name="Sugar",
            buying_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            number_of_commodity=10,
            amount=Decimal("100.00"),
            total_amount=Decimal("1000.00"),
        )
        Stock.objects.filter(customer=self.customer, commodity=commodity).update(
            number_of_commodity=10
        )

        response = self.client.post(
            reverse("sales"),
            {
                "customer_name": "Alice",
                "name": "Sugar",
                "number_of_commodity": 2,
                "selling_price": "150.00",
                "amount": "300.00",
                "payment_type": Sales.PaymentType.CREDIT,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("sales"))
        self.assertEqual(Sales.objects.count(), 1)
        self.assertEqual(Debtors.objects.count(), 1)

        sale = Sales.objects.get()
        debt = Debtors.objects.get()
        self.assertEqual(sale.payment_type, Sales.PaymentType.CREDIT)
        self.assertEqual(sale.buyer_name, "Alice")
        self.assertEqual(debt.sale, sale)
        self.assertEqual(debt.customer_name, "Alice")
        self.assertEqual(debt.commodity_name, "Sugar")
        self.assertEqual(debt.number_of_commodity, 2)
        self.assertEqual(debt.total_amount, Decimal("300.00"))
        self.assertEqual(DebtorLedger.objects.filter(debtor=debt).count(), 1)
        ledger = DebtorLedger.objects.get(debtor=debt)
        self.assertEqual(ledger.debit, Decimal("300.00"))
        self.assertEqual(ledger.credit, Decimal("0.00"))
        self.assertEqual(ledger.balance, Decimal("300.00"))

    def test_credit_sale_updates_existing_debtor_record(self):
        commodity = Commodity.objects.create(
            customer=self.customer,
            name="Sugar",
            buying_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            number_of_commodity=10,
            amount=Decimal("100.00"),
            total_amount=Decimal("1000.00"),
        )
        Stock.objects.filter(customer=self.customer, commodity=commodity).update(
            number_of_commodity=10
        )

        self.client.post(
            reverse("sales"),
            {
                "customer_name": "Alice",
                "name": "Sugar",
                "number_of_commodity": 2,
                "selling_price": "150.00",
                "amount": "300.00",
                "payment_type": Sales.PaymentType.CREDIT,
            },
            follow=True,
        )

        self.client.post(
            reverse("sales"),
            {
                "customer_name": "Alice",
                "name": "Sugar",
                "number_of_commodity": 3,
                "selling_price": "150.00",
                "amount": "450.00",
                "payment_type": Sales.PaymentType.CREDIT,
            },
            follow=True,
        )

        self.assertEqual(Sales.objects.count(), 2)
        self.assertEqual(Debtors.objects.count(), 1)
        debt = Debtors.objects.get()
        self.assertEqual(debt.customer_name, "Alice")
        self.assertEqual(debt.number_of_commodity, 5)
        self.assertEqual(debt.total_amount, Decimal("750.00"))
        self.assertEqual(DebtorLedger.objects.filter(debtor=debt).count(), 2)
        latest_ledger = DebtorLedger.objects.filter(debtor=debt).order_by("-date", "-id").first()
        self.assertEqual(latest_ledger.balance, Decimal("750.00"))

    def test_credit_payment_reduces_debtor_balance(self):
        commodity = Commodity.objects.create(
            customer=self.customer,
            name="Sugar",
            buying_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            number_of_commodity=10,
            amount=Decimal("100.00"),
            total_amount=Decimal("1000.00"),
        )
        Stock.objects.filter(customer=self.customer, commodity=commodity).update(
            number_of_commodity=10
        )

        self.client.post(
            reverse("sales"),
            {
                "customer_name": "Alice",
                "name": "Sugar",
                "number_of_commodity": 4,
                "selling_price": "150.00",
                "amount": "600.00",
                "payment_type": Sales.PaymentType.CREDIT,
            },
            follow=True,
        )

        response = self.client.post(
            reverse("credit_payment"),
            {
                "customer_name": "Alice",
                "payment_amount": "200.00",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("credit_payment"))
        debt = Debtors.objects.get()
        self.assertEqual(debt.total_amount, Decimal("400.00"))
        self.assertEqual(Payment.objects.filter(debtor=debt).count(), 1)
        latest_ledger = DebtorLedger.objects.filter(debtor=debt).order_by("-date", "-id").first()
        self.assertEqual(latest_ledger.credit, Decimal("200.00"))
        self.assertEqual(latest_ledger.balance, Decimal("400.00"))

    def test_credit_payment_overpay_clears_balance(self):
        commodity = Commodity.objects.create(
            customer=self.customer,
            name="Sugar",
            buying_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            number_of_commodity=10,
            amount=Decimal("100.00"),
            total_amount=Decimal("1000.00"),
        )
        Stock.objects.filter(customer=self.customer, commodity=commodity).update(
            number_of_commodity=10
        )

        self.client.post(
            reverse("sales"),
            {
                "customer_name": "Alice",
                "name": "Sugar",
                "number_of_commodity": 2,
                "selling_price": "150.00",
                "amount": "300.00",
                "payment_type": Sales.PaymentType.CREDIT,
            },
            follow=True,
        )

        response = self.client.post(
            reverse("credit_payment"),
            {
                "customer_name": "Alice",
                "payment_amount": "500.00",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("credit_payment"))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Payment applied successfully. Debt cleared.", messages)
        debt = Debtors.objects.get()
        self.assertEqual(debt.total_amount, Decimal("0.00"))
        self.assertTrue(debt.is_cleared)


class DebtorModuleApiTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            business_name="Ledger Shop",
            email="ledger@example.com",
            phone_number="0700000099",
            password="hashed-password",
            confirm_password="hashed-password",
        )
        session = self.client.session
        session["customer_id"] = self.customer.id
        session["customer_business_name"] = self.customer.business_name
        session.save()

        self.commodity = Commodity.objects.create(
            customer=self.customer,
            name="Rice",
            buying_price=Decimal("90.00"),
            selling_price=Decimal("120.00"),
            number_of_commodity=20,
            amount=Decimal("1800.00"),
            total_amount=Decimal("1800.00"),
        )
        Stock.objects.filter(customer=self.customer, commodity=self.commodity).update(
            number_of_commodity=20
        )

        self.client.post(
            reverse("sales"),
            {
                "customer_name": "Alice",
                "name": "Rice",
                "number_of_commodity": 3,
                "selling_price": "120.00",
                "amount": "360.00",
                "payment_type": Sales.PaymentType.CREDIT,
            },
            follow=True,
        )
        self.debtor = Debtors.objects.get(customer_name="Alice")

    def test_debtor_ledger_api_returns_running_balance(self):
        response = self.client.get(reverse("debtor_ledger_api"), {"name": "Alice"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["exists"])
        self.assertEqual(payload["debtor"]["name"], "Alice")
        self.assertEqual(payload["total_balance"], 360.0)
        self.assertEqual(len(payload["entries"]), 1)
        self.assertEqual(payload["entries"][0]["debit"], 360.0)
        self.assertEqual(payload["entries"][0]["balance"], 360.0)

    def test_pay_debt_api_creates_payment_and_updates_ledger(self):
        response = self.client.post(
            reverse("pay_debt_api"),
            data='{"name":"Alice","amount_paid":100,"method":"bank","reference":"TXN-1"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], "Payment successful")
        self.assertEqual(payload["remaining_credit"], 260.0)
        self.assertFalse(payload["cleared"])
        self.assertEqual(payload["applied_amount"], 100.0)

        self.debtor.refresh_from_db()
        self.assertEqual(self.debtor.total_amount, Decimal("260.00"))
        payment = Payment.objects.get(debtor=self.debtor)
        self.assertEqual(payment.method, Payment.Method.BANK)
        self.assertEqual(payment.reference, "TXN-1")

        latest_ledger = DebtorLedger.objects.filter(debtor=self.debtor).order_by("-date", "-id").first()
        self.assertEqual(latest_ledger.credit, Decimal("100.00"))
        self.assertEqual(latest_ledger.balance, Decimal("260.00"))

    def test_payment_history_api_returns_recorded_payments(self):
        self.client.post(
            reverse("pay_debt_api"),
            data='{"name":"Alice","amount_paid":80,"method":"cash","reference":"RCP-80"}',
            content_type="application/json",
        )

        response = self.client.get(reverse("payment_history_api"), {"name": "Alice"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["exists"])
        self.assertEqual(len(payload["payments"]), 1)
        self.assertEqual(payload["payments"][0]["amount_paid"], 80.0)
        self.assertEqual(payload["payments"][0]["method"], "cash")
        self.assertEqual(payload["payments"][0]["reference"], "RCP-80")

    def test_overdue_debtors_api_returns_overdue_rows(self):
        self.debtor.due_date = timezone.localdate() - timedelta(days=2)
        self.debtor.save(update_fields=["due_date"])

        response = self.client.get(reverse("overdue_debtors_api"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["name"], "Alice")
        self.assertEqual(payload["items"][0]["status"], "overdue")


class InventorySyncTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            business_name="Sync Shop",
            email="sync@example.com",
            phone_number="0700000002",
            password="hashed-password",
            confirm_password="hashed-password",
        )

    def test_add_stock_merges_existing_commodity_by_name(self):
        commodity = Commodity.add_stock(
            customer=self.customer,
            name="Rice",
            quantity=5,
            buying_price="10.00",
            selling_price="15.00",
            amount="10.00",
        )

        Commodity.add_stock(
            customer=self.customer,
            name="Rice",
            quantity=7,
            buying_price="10.00",
            selling_price="16.00",
            amount="10.00",
        )

        commodity.refresh_from_db()
        stock_item = Stock.objects.get(customer=self.customer, commodity=commodity)
        self.assertEqual(Commodity.objects.filter(customer=self.customer, name="Rice").count(), 1)
        self.assertEqual(commodity.number_of_commodity, 12)
        self.assertEqual(stock_item.number_of_commodity, 12)

    def test_stock_reduction_updates_matching_commodity(self):
        commodity = Commodity.add_stock(
            customer=self.customer,
            name="Beans",
            quantity=9,
            buying_price="8.00",
            selling_price="12.00",
            amount="8.00",
        )
        stock_item = Stock.objects.get(customer=self.customer, commodity=commodity)

        stock_item.reduce_quantity(4)

        commodity.refresh_from_db()
        stock_item.refresh_from_db()
        self.assertEqual(stock_item.number_of_commodity, 5)
        self.assertEqual(commodity.number_of_commodity, 5)

    def test_negative_stock_is_blocked(self):
        commodity = Commodity.add_stock(
            customer=self.customer,
            name="Flour",
            quantity=3,
            buying_price="20.00",
            selling_price="25.00",
            amount="20.00",
        )
        stock_item = Stock.objects.get(customer=self.customer, commodity=commodity)

        with self.assertRaises(ValidationError):
            stock_item.reduce_quantity(4)

        commodity.refresh_from_db()
        stock_item.refresh_from_db()
        self.assertEqual(stock_item.number_of_commodity, 3)
        self.assertEqual(commodity.number_of_commodity, 3)

    def test_add_stock_updates_running_totals(self):
        rice = Commodity.add_stock(
            customer=self.customer,
            name="Rice",
            quantity=5,
            buying_price="10.00",
            selling_price="15.00",
            amount="10.00",
        )
        beans = Commodity.add_stock(
            customer=self.customer,
            name="Beans",
            quantity=4,
            buying_price="8.00",
            selling_price="12.00",
            amount="8.00",
        )

        rice_stock = Stock.objects.get(customer=self.customer, commodity=rice)
        beans_stock = Stock.objects.get(customer=self.customer, commodity=beans)

        self.assertEqual(rice_stock.amount, Decimal("50.00"))
        self.assertEqual(rice_stock.expected_sales, Decimal("75.00"))
        self.assertEqual(beans_stock.amount, Decimal("32.00"))
        self.assertEqual(beans_stock.expected_sales, Decimal("48.00"))

        self.assertEqual(rice_stock.total_amount, Decimal("50.00"))
        self.assertEqual(rice_stock.expected_total, Decimal("75.00"))
        self.assertEqual(beans_stock.total_amount, Decimal("82.00"))
        self.assertEqual(beans_stock.expected_total, Decimal("123.00"))

    def test_reduce_quantity_recalculates_totals(self):
        commodity = Commodity.add_stock(
            customer=self.customer,
            name="Sugar",
            quantity=10,
            buying_price="100.00",
            selling_price="150.00",
            amount="100.00",
        )
        stock_item = Stock.objects.get(customer=self.customer, commodity=commodity)

        stock_item.reduce_quantity(4)

        stock_item.refresh_from_db()
        self.assertEqual(stock_item.number_of_commodity, 6)
        self.assertEqual(stock_item.amount, Decimal("600.00"))
        self.assertEqual(stock_item.expected_sales, Decimal("900.00"))
        self.assertEqual(stock_item.total_amount, Decimal("600.00"))
        self.assertEqual(stock_item.expected_total, Decimal("900.00"))


class GlobalSearchTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            business_name="Search Shop",
            email="search@example.com",
            phone_number="0700000003",
            password="hashed-password",
            confirm_password="hashed-password",
        )
        session = self.client.session
        session["customer_id"] = self.customer.id
        session["customer_business_name"] = self.customer.business_name
        session.save()

        self.commodity = Commodity.add_stock(
            customer=self.customer,
            name="Rice",
            quantity=12,
            buying_price="90.00",
            selling_price="120.00",
            amount="90.00",
        )

        self.sale = Sales.objects.create(
            commodity=self.commodity,
            buyer_name="Alice",
            payment_type=Sales.PaymentType.CREDIT,
            name="Rice",
            buying_price=Decimal("90.00"),
            selling_price=Decimal("120.00"),
            number_of_commodity=2,
            amount=Decimal("240.00"),
            total_amount=Decimal("240.00"),
        )
        Debtors.objects.create(
            name="Alice",
            sale=self.sale,
            customer_name="Alice",
            commodity_name="Rice",
            number_of_commodity=2,
            amount=Decimal("240.00"),
            total_amount=Decimal("240.00"),
        )
        Expense.objects.create(
            customer=self.customer,
            description="Rent",
            amount=Decimal("1000.00"),
        )
        ReturnEntry.objects.create(
            customer=self.customer,
            return_type=ReturnEntry.ReturnType.RETURN_IN,
            amount=Decimal("50.00"),
            note="Rice bag damaged",
        )

    def test_global_search_page_returns_matches(self):
        response = self.client.get(reverse("search"), {"q": "Rice"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Global Search Results")
        self.assertContains(response, "Rice")
        self.assertContains(response, "<mark>Rice</mark>", html=False)

    def test_global_search_page_finds_customer_credit_matches(self):
        response = self.client.get(reverse("search"), {"q": "Alice"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customers and Credit")
        self.assertContains(response, "Alice")

    def test_autocomplete_returns_suggestions(self):
        response = self.client.get(reverse("search_suggestions_api"), {"q": "Ri"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("suggestions", payload)
        suggestion_values = [item["value"] for item in payload["suggestions"]]
        self.assertIn("Rice", suggestion_values)

    def test_autocomplete_requires_authenticated_customer(self):
        self.client.session.flush()

        response = self.client.get(reverse("search_suggestions_api"), {"q": "Rice"})
        self.assertEqual(response.status_code, 401)
