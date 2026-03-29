document.addEventListener("DOMContentLoaded", function () {

    const quantityInput = document.getElementById("id_number_of_commodity");
    const priceInput = document.getElementById("id_selling_price");
    const buyingInput = document.getElementById("id_buying_price");
    const nameInput = document.getElementById("id_name");
    const totalDisplay = document.getElementById("total");
    const amountInput = document.getElementById("id_amount");

    function calculateTotal() {
        const num_of_commodity = parseFloat(quantityInput.value) || 0;
        const price = parseFloat(priceInput.value) || 0;
        const total = num_of_commodity * price;
        totalDisplay.textContent = total.toFixed(2);
        if (amountInput) {
            amountInput.value = total.toFixed(2);
        }
    }

    quantityInput.addEventListener("input", calculateTotal);
    priceInput.addEventListener("input", calculateTotal);

    let lastFetchedName = "";
    let fetchedForName = false;
    let buyingDirty = false;
    let sellingDirty = false;

    if (buyingInput) {
        buyingInput.addEventListener("input", () => {
            buyingDirty = true;
        });
    }
    if (priceInput) {
        priceInput.addEventListener("input", () => {
            sellingDirty = true;
        });
    }

    const fetchProductDetails = async (productName) => {
        if (!productName || !nameInput) return;
        const nameKey = productName.trim().toLowerCase();

        if (nameKey === lastFetchedName && fetchedForName) {
            return;
        }

        lastFetchedName = nameKey;
        fetchedForName = true;
        buyingDirty = false;
        sellingDirty = false;

        try {
            const response = await fetch(
                `/api/product-details/?name=${encodeURIComponent(productName)}`
            );
            if (!response.ok) return;
            const data = await response.json();

            if (data && data.product_name) {
                if (buyingInput && !buyingDirty && data.buying_price !== null) {
                    buyingInput.value = Number(data.buying_price).toFixed(2);
                }
                if (priceInput && !sellingDirty && data.selling_price !== null) {
                    priceInput.value = Number(data.selling_price).toFixed(2);
                }
                calculateTotal();
            }
        } catch (err) {
            // Silent fail: keep manual entry flow.
        }
    };

    const debounce = (fn, wait = 350) => {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), wait);
        };
    };

    const debouncedLookup = debounce((value) => fetchProductDetails(value));

    if (nameInput) {
        nameInput.addEventListener("input", () => {
            fetchedForName = false;
            debouncedLookup(nameInput.value);
        });
        nameInput.addEventListener("change", () => {
            fetchedForName = false;
            fetchProductDetails(nameInput.value);
        });
        nameInput.addEventListener("blur", () => {
            fetchProductDetails(nameInput.value);
        });
    }

    calculateTotal();

});
