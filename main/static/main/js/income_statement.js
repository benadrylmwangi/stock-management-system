function getTotalAmountByDate(dateValue, tableId = "stockTotalsTable") {
    if (!dateValue) {
        return null;
    }

    const table = document.getElementById(tableId);
    if (!table) {
        return null;
    }

    const rows = table.querySelectorAll("tbody tr[data-date]");
    let matchedTotal = null;
    rows.forEach((row) => {
        if (row.getAttribute("data-date") === dateValue) {
            const cell = row.querySelector(".total-amount");
            if (cell) {
                matchedTotal = cell.textContent.trim();
            }
        }
    });

    return matchedTotal;
}

function getSalesTotalByDate(dateValue, tableId = "commodityTotalsTable") {
    if (!dateValue) {
        return null;
    }

    const table = document.getElementById(tableId);
    if (!table) {
        return null;
    }

    const rows = table.querySelectorAll("tbody tr[data-date]");
    let matchedTotal = null;
    rows.forEach((row) => {
        if (row.getAttribute("data-date") === dateValue) {
            const cell = row.querySelector(".sales-total");
            if (cell) {
                matchedTotal = cell.textContent.trim();
            }
        }
    });

    return matchedTotal;
}

function parseNumber(value) {
    if (value === null || value === undefined) {
        return 0;
    }
    const cleaned = String(value).replace(/,/g, "").trim();
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
}

document.addEventListener("DOMContentLoaded", function () {
    const button = document.getElementById("lookup-total-btn");
    const input = document.getElementById("lookup-date");
    const result = document.getElementById("lookup-result");
    const table = document.getElementById("stockTotalsTable");
    const heading = document.getElementById("stockTotalsHeading");
    const toggle = document.getElementById("toggle-table");
    const commodityResult = document.getElementById("commodity-result");
    const commodityTable = document.getElementById("commodityTotalsTable");
    const commodityHeading = document.getElementById("commodityTotalsHeading");
    const commodityToggle = document.getElementById("toggle-commodity-table");

    if (
        !button ||
        !input ||
        !result ||
        !table ||
        !heading ||
        !toggle ||
        !commodityResult ||
        !commodityTable ||
        !commodityHeading ||
        !commodityToggle
    ) {
        return;
    }

    function updateVisibility(hasMatch) {
        if (toggle.checked && hasMatch) {
            table.style.display = "";
            heading.style.display = "";
        } else {
            table.style.display = "none";
            heading.style.display = "none";
        }
    }

    function updateCommodityVisibility(hasMatch) {
        if (commodityToggle.checked && hasMatch) {
            commodityTable.style.display = "";
            commodityHeading.style.display = "";
        } else {
            commodityTable.style.display = "none";
            commodityHeading.style.display = "none";
        }
    }

    button.addEventListener("click", function () {
        const dateValue = input.value;
        const rows = table.querySelectorAll("tbody tr[data-date]");
        let hasMatch = false;
        rows.forEach((row) => {
            if (row.getAttribute("data-date") === dateValue) {
                row.style.display = "";
                hasMatch = true;
            } else {
                row.style.display = "none";
            }
        });

        if (!hasMatch) {
            updateVisibility(false);
            result.textContent = "No match";
            return;
        }

        updateVisibility(true);
        const total = getTotalAmountByDate(dateValue);
        result.textContent = total === null ? "No match" : total;

        const salesTotal = getSalesTotalByDate(dateValue);
        commodityResult.textContent = salesTotal === null ? "No match" : salesTotal;

        const commodityRows = commodityTable.querySelectorAll("tbody tr[data-date]");
        let commodityHasMatch = false;
        commodityRows.forEach((row) => {
            if (row.getAttribute("data-date") === dateValue) {
                row.style.display = "";
                commodityHasMatch = true;
            } else {
                row.style.display = "none";
            }
        });
        updateCommodityVisibility(commodityHasMatch);
    });

    toggle.addEventListener("change", function () {
        const dateValue = input.value;
        const rows = table.querySelectorAll("tbody tr[data-date]");
        const hasMatch = Array.from(rows).some(
            (row) => row.getAttribute("data-date") === dateValue && row.style.display !== "none"
        );
        updateVisibility(hasMatch);
    });

    commodityToggle.addEventListener("change", function () {
        const dateValue = input.value;
        const rows = commodityTable.querySelectorAll("tbody tr[data-date]");
        const hasMatch = Array.from(rows).some(
            (row) => row.getAttribute("data-date") === dateValue && row.style.display !== "none"
        );
        updateCommodityVisibility(hasMatch);
    });
});

// -----------------------------
// Income Statement (date range)
// -----------------------------
(() => {
    const startInput = document.getElementById("incomeStartDate");
    const endInput = document.getElementById("incomeEndDate");
    const generateBtn = document.getElementById("generateIncomeBtn");
    const downloadBtn = document.getElementById("downloadIncomeBtn");
    const errorEl = document.getElementById("incomeError");
    const titleEl = document.getElementById("statementTitle");

    if (!startInput || !endInput || !generateBtn || !downloadBtn) {
        return;
    }

    const formatAmount = (value) => {
        const num = Number(value || 0);
        if (num < 0) {
            return `(${Math.abs(num).toFixed(2)})`;
        }
        return num.toFixed(2);
    };

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = value;
        }
    };

    const renderStatement = (data) => {
        const sales = parseNumber(data.sales);
        const salesReturns = parseNumber(data.sales_returns);
        const openingInventory = parseNumber(data.opening_inventory);
        const purchases = parseNumber(data.purchases);
        const returnInwards = parseNumber(data.return_inwards);
        const closingInventory = parseNumber(data.closing_inventory);
        const discountReceived = parseNumber(data.discount_received);

        const expenses = data.expenses || {};
        const wages = parseNumber(expenses.wages);
        const lighting = parseNumber(expenses.lighting);
        const rent = parseNumber(expenses.rent);
        const general = parseNumber(expenses.general);
        const carriage = parseNumber(expenses.carriage_outwards);

        const netSales = sales - salesReturns;
        const netPurchases = purchases - returnInwards;
        const goodsAvailable = openingInventory + netPurchases;
        const costOfSales = goodsAvailable - closingInventory;
        const grossProfit = netSales - costOfSales;
        const totalIncome = grossProfit + discountReceived;
        const totalExpenses = wages + lighting + rent + general + carriage;
        const netProfit = totalIncome - totalExpenses;

        setText("salesAmount", formatAmount(sales));
        setText("salesReturnsAmount", formatAmount(-salesReturns));
        setText("netSalesAmount", formatAmount(netSales));

        setText("openingInventoryAmount", formatAmount(openingInventory));
        setText("purchasesAmount", formatAmount(purchases));
        setText("returnInwardsAmount", formatAmount(-returnInwards));
        setText("netPurchasesAmount", formatAmount(netPurchases));
        setText("goodsAvailableAmount", formatAmount(goodsAvailable));
        setText("closingInventoryAmount", formatAmount(-closingInventory));
        setText("costOfSalesAmount", formatAmount(costOfSales));

        setText("grossProfitAmount", formatAmount(grossProfit));
        setText("discountReceivedAmount", formatAmount(discountReceived));
        setText("totalIncomeAmount", formatAmount(totalIncome));

        setText("wagesAmount", formatAmount(wages));
        setText("lightingAmount", formatAmount(lighting));
        setText("rentAmount", formatAmount(rent));
        setText("generalAmount", formatAmount(general));
        setText("carriageAmount", formatAmount(carriage));
        setText("totalExpensesAmount", formatAmount(totalExpenses));
        setText("netProfitAmount", formatAmount(netProfit));
    };

    generateBtn.addEventListener("click", async () => {
        const startDate = startInput.value;
        const endDate = endInput.value;
        errorEl.textContent = "";

        if (!startDate || !endDate) {
            errorEl.textContent = "Please select both start and end dates.";
            return;
        }

        titleEl.textContent = `Income Statement for the Period Ended ${endDate}`;

        try {
            const response = await fetch(
                `/api/income-statement/?start_date=${startDate}&end_date=${endDate}`
            );
            if (!response.ok) {
                const payload = await response.json();
                throw new Error(payload.error || "Unable to fetch income statement data.");
            }
            const data = await response.json();
            renderStatement(data);
        } catch (err) {
            errorEl.textContent = err.message || "Unable to fetch income statement data.";
        }
    });

    downloadBtn.addEventListener("click", () => {
        window.print();
    });
})();
