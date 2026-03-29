function trade(dateValue) {
    updateTradingSummary(dateValue || null);
}

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

function sumAmountsByDate(tableId, dateValue, dataKey = "amount") {
    const table = document.getElementById(tableId);
    if (!table) {
        return 0;
    }

    const rows = table.querySelectorAll("tbody tr[data-date]");
    let total = 0;
    rows.forEach((row) => {
        if (dateValue && row.getAttribute("data-date") !== dateValue) {
            return;
        }
        const value = row.getAttribute(`data-${dataKey}`);
        total += parseNumber(value);
    });
    return total;
}

function sumReturnByType(dateValue, returnType) {
    const table = document.getElementById("returnsTable");
    if (!table) {
        return 0;
    }

    const rows = table.querySelectorAll("tbody tr[data-date]");
    let total = 0;
    rows.forEach((row) => {
        const rowType = row.getAttribute("data-type");
        if (rowType !== returnType) {
            return;
        }
        if (dateValue && row.getAttribute("data-date") !== dateValue) {
            return;
        }
        total += parseNumber(row.getAttribute("data-amount"));
    });
    return total;
}

function updateTradingSummary(dateValue) {
    const salesTotal = sumAmountsByDate("commodityTotalsTable", dateValue, "amount");
    const costTotal = sumAmountsByDate("commodityTotalsTable", dateValue, "cost");
    const returnInTotal = sumReturnByType(dateValue, "IN");
    const returnOutTotal = sumReturnByType(dateValue, "OUT");
    const expenseTotal = sumAmountsByDate("expensesTable", dateValue, "amount");

    const netSales = salesTotal - returnInTotal;
    const costOfSales = costTotal - returnOutTotal;
    const grossProfit = netSales - costOfSales;
    const netProfit = grossProfit - expenseTotal;

    const salesEl = document.getElementById("trading-sales");
    const returnInEl = document.getElementById("trading-return-in");
    const netSalesEl = document.getElementById("trading-net-sales");
    const costEl = document.getElementById("trading-cost");
    const returnOutEl = document.getElementById("trading-return-out");
    const grossEl = document.getElementById("trading-gross");
    const expenseEl = document.getElementById("trading-expenses");
    const netEl = document.getElementById("trading-net");

    if (!salesEl || !returnInEl || !netSalesEl || !costEl || !returnOutEl || !grossEl || !expenseEl || !netEl) {
        return;
    }

    salesEl.textContent = salesTotal.toFixed(2);
    returnInEl.textContent = returnInTotal.toFixed(2);
    netSalesEl.textContent = netSales.toFixed(2);
    costEl.textContent = costOfSales.toFixed(2);
    returnOutEl.textContent = returnOutTotal.toFixed(2);
    grossEl.textContent = grossProfit.toFixed(2);
    expenseEl.textContent = expenseTotal.toFixed(2);
    netEl.textContent = netProfit.toFixed(2);
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
    const downloadButton = document.getElementById("download-trading-pdf");

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
        !commodityToggle ||
        !downloadButton
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

        trade(dateValue);
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

    downloadButton.addEventListener("click", function () {
        const dateValue = input.value;
        const url = dateValue ? `/trading_report/?date=${encodeURIComponent(dateValue)}` : "/trading_report/";
        window.location.href = url;
    });

    trade(null);
});

// -----------------------------
// Trading Profit and Loss (date range)
// -----------------------------
(() => {
    // Mock data (sample transactions)
    const sales = [
        { date: "2026-01-05", amount: 12000 },
        { date: "2026-01-18", amount: 8500 },
        { date: "2026-02-02", amount: 14900 },
        { date: "2026-03-12", amount: 17650 },
        { date: "2026-03-22", amount: 9100 }
    ];

    const returns = [
        { date: "2026-01-20", amount: 900 },
        { date: "2026-02-10", amount: 450 },
        { date: "2026-03-18", amount: 1200 }
    ];

    const purchases = [
        { date: "2026-01-03", amount: 7000 },
        { date: "2026-01-28", amount: 5200 },
        { date: "2026-02-14", amount: 6100 },
        { date: "2026-03-05", amount: 8300 },
        { date: "2026-03-20", amount: 4100 }
    ];

    const expenses = [
        { date: "2026-01-10", type: "Transport", amount: 650 },
        { date: "2026-01-31", type: "Rent", amount: 1800 },
        { date: "2026-02-08", type: "Electricity etc", amount: 420 },
        { date: "2026-02-28", type: "Rent", amount: 1800 },
        { date: "2026-03-07", type: "Transport", amount: 530 },
        { date: "2026-03-22", type: "Electricity etc", amount: 460 }
    ];

    const stock = [
        { date: "2026-01-01", opening: 5000, closing: 6200 },
        { date: "2026-02-01", opening: 6200, closing: 5900 },
        { date: "2026-03-01", opening: 5900, closing: 6100 }
    ];

    let latestReportText = "";

    // Helpers
    const parseDate = (d) => new Date(`${d}T00:00:00`);

    const inRange = (dateStr, start, end) => {
        const d = parseDate(dateStr).getTime();
        return d >= start && d <= end;
    };

    const sumAmounts = (items) =>
        items.reduce((total, item) => total + (item.amount || 0), 0);

    const formatAmount = (value, forceBrackets = false) => {
        const num = Number(value) || 0;
        const absText = Math.abs(num).toFixed(0);
        if (forceBrackets || num < 0) return `(${absText})`;
        return absText;
    };

    const padLine = (label, value, width = 32) => {
        const labelText = label.padEnd(width, " ");
        return `${labelText}${value}`;
    };

    // Required functions
    const getFilteredData = (startDate, endDate) => {
        const start = parseDate(startDate).getTime();
        const end = parseDate(endDate).getTime();

        const filteredSales = sales.filter((s) => inRange(s.date, start, end));
        const filteredReturns = returns.filter((r) => inRange(r.date, start, end));
        const filteredPurchases = purchases.filter((p) => inRange(p.date, start, end));
        const filteredExpenses = expenses.filter((e) => inRange(e.date, start, end));

        // Opening stock = latest opening on or before start date
        const openingStock = stock
            .filter((s) => parseDate(s.date).getTime() <= start)
            .sort((a, b) => parseDate(b.date) - parseDate(a.date))[0]?.opening || 0;

        // Closing stock = latest closing on or before end date
        const closingStock = stock
            .filter((s) => parseDate(s.date).getTime() <= end)
            .sort((a, b) => parseDate(b.date) - parseDate(a.date))[0]?.closing || 0;

        return {
            sales: filteredSales,
            returns: filteredReturns,
            purchases: filteredPurchases,
            expenses: filteredExpenses,
            openingStock,
            closingStock
        };
    };

    const calculatePL = (data) => {
        const totalSales = sumAmounts(data.sales);
        const totalReturns = sumAmounts(data.returns);
        const netSales = totalSales - totalReturns;

        const totalPurchases = sumAmounts(data.purchases);
        const costOfSales = data.openingStock + totalPurchases - data.closingStock;

        const grossProfit = netSales - costOfSales;

        const expenseTotals = data.expenses.reduce((acc, item) => {
            acc[item.type] = (acc[item.type] || 0) + item.amount;
            return acc;
        }, {});

        const totalExpenses = Object.values(expenseTotals).reduce(
            (sum, val) => sum + val,
            0
        );

        const netProfit = grossProfit - totalExpenses;

        return {
            totalSales,
            totalReturns,
            netSales,
            costOfSales,
            grossProfit,
            expenseTotals,
            totalExpenses,
            netProfit
        };
    };

    const renderPL = (result) => {
        const lines = [];
        lines.push("----------------------------------");
        lines.push("TRADING PROFIT AND LOSS ACCOUNT");
        lines.push("----------------------------------");
        lines.push("");
        lines.push(padLine("Sales:", formatAmount(result.totalSales)));
        lines.push(padLine("Less: Sales Return:", formatAmount(result.totalReturns, true)));
        lines.push(padLine("Net Sales:", formatAmount(result.netSales)));
        lines.push("");
        lines.push(padLine("Less: Cost of Sales:", formatAmount(result.costOfSales, true)));
        lines.push("");
        lines.push(padLine("Gross Profit / Loss:", formatAmount(result.grossProfit)));
        lines.push("");
        lines.push("Less Expenses:");

        const expenseOrder = ["Transport", "Rent", "Electricity etc"];
        expenseOrder.forEach((type) => {
            const value = result.expenseTotals[type] || 0;
            lines.push(padLine(`   ${type}:`, formatAmount(value)));
        });

        lines.push(padLine("Total Expenses:", formatAmount(result.totalExpenses, true)));
        lines.push("");
        lines.push(padLine("Net Profit:", formatAmount(result.netProfit)));
        lines.push("----------------------------------");

        latestReportText = lines.join("\n");

        const plResult = document.getElementById("plResult");
        if (!plResult) return;

        plResult.innerHTML = "";
        const pre = document.createElement("pre");
        pre.textContent = latestReportText;
        plResult.appendChild(pre);
    };

    const downloadPL = () => {
        if (!latestReportText) return;

        const blob = new Blob([latestReportText], { type: "text/plain" });
        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = "trading_profit_and_loss.txt";
        document.body.appendChild(a);
        a.click();

        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    // UI wiring
    document.addEventListener("DOMContentLoaded", () => {
        const generateBtn = document.getElementById("generatePLBtn");
        const startInput = document.getElementById("startDate");
        const endInput = document.getElementById("endDate");
        const plResult = document.getElementById("plResult");

        if (!generateBtn || !startInput || !endInput || !plResult) return;

        let downloadBtn = document.getElementById("downloadPLBtn");
        if (!downloadBtn) {
            downloadBtn = document.createElement("button");
            downloadBtn.id = "downloadPLBtn";
            downloadBtn.textContent = "Download Report";
            plResult.insertAdjacentElement("afterend", downloadBtn);
        }

        generateBtn.addEventListener("click", () => {
            const startDate = startInput.value;
            const endDate = endInput.value;
            if (!startDate || !endDate) return;

            const filtered = getFilteredData(startDate, endDate);
            const result = calculatePL(filtered);
            renderPL(result);
        });

        downloadBtn.addEventListener("click", downloadPL);
    });
})();
