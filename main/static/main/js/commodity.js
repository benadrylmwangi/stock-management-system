document.addEventListener("DOMContentLoaded", function () {

    console.log("Commodity JS loaded v20260315");

    const quantityInput = document.getElementById("quantity");
    const buyingInput = document.getElementById("buying_price");
    const sellingInput = document.getElementById("expected_selling_price");

    const amountInput = document.getElementById("amount");
    const expectedSalesInput = document.getElementById("expected_sales");

    if (
        !quantityInput ||
        !buyingInput ||
        !sellingInput ||
        !amountInput ||
        !expectedSalesInput
    ) {
        console.warn("Commodity JS: required inputs not found on this page.");
        return;
    }

    function calculateValues() {

        let quantity = parseFloat(quantityInput.value) || 0;
        let buyingPrice = parseFloat(buyingInput.value) || 0;
        let sellingPrice = parseFloat(sellingInput.value) || 0;

        let amount = quantity * buyingPrice;
        let expectedSales = quantity * sellingPrice;

        amountInput.value = amount.toFixed(2);
        expectedSalesInput.value = expectedSales.toFixed(2);
    }

    // Update on typing and on value commits (e.g., number spinners).
    ["input", "change", "blur"].forEach((evt) => {
        quantityInput.addEventListener(evt, calculateValues);
        buyingInput.addEventListener(evt, calculateValues);
        sellingInput.addEventListener(evt, calculateValues);
    });

    // Populate calculated fields if inputs already have values.
    calculateValues();

    // Optional smoke test: append ?commodityTest=1 to the URL.
    const params = new URLSearchParams(window.location.search);
    if (params.has("commodityTest")) {
        const original = {
            quantity: quantityInput.value,
            buying: buyingInput.value,
            selling: sellingInput.value
        };

        quantityInput.value = "2";
        buyingInput.value = "3.50";
        sellingInput.value = "4.25";
        calculateValues();

        const amountOk = amountInput.value === "7.00";
        const expectedOk = expectedSalesInput.value === "8.50";

        if (amountOk && expectedOk) {
            console.log("Commodity JS smoke test: PASS");
        } else {
            console.error(
                "Commodity JS smoke test: FAIL",
                { amount: amountInput.value, expected: expectedSalesInput.value }
            );
        }

        // Restore original values after test
        quantityInput.value = original.quantity;
        buyingInput.value = original.buying;
        sellingInput.value = original.selling;
        calculateValues();
    }
});
