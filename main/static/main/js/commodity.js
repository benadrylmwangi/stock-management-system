document.addEventListener('DOMContentLoaded', function () {
    const quantity = document.getElementById('quantity');
    const buyingPrice = document.getElementById('buying_price');
    const sellingPrice = document.getElementById('selling_price');
    const amount = document.getElementById('amount');
    const totalAmount = document.getElementById('total_amount');

    function calculateTotals() {
        const qty = parseFloat(quantity.value) || 0;
        const buy = parseFloat(buyingPrice.value) || 0;
        const sell = parseFloat(sellingPrice.value) || 0;

        amount.value = (qty * buy).toFixed(2);
        totalAmount.value = (qty * sell).toFixed(2);
    }

    quantity.addEventListener('input', calculateTotals);
    buyingPrice.addEventListener('input', calculateTotals);
    sellingPrice.addEventListener('input', calculateTotals);
});