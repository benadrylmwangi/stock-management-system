(() => {
  const startInput = document.getElementById("cashbookStartDate");
  const endInput = document.getElementById("cashbookEndDate");
  const generateBtn = document.getElementById("cashbookGenerate");
  const printBtn = document.getElementById("cashbookPrint");
  const tbody = document.getElementById("cashbookBody");
  const errorEl = document.getElementById("cashbookError");
  const rangeEl = document.getElementById("cashbookRange");

  const receiptCashTotal = document.getElementById("receiptCashTotal");
  const receiptBankTotal = document.getElementById("receiptBankTotal");
  const receiptDiscTotal = document.getElementById("receiptDiscTotal");
  const paymentCashTotal = document.getElementById("paymentCashTotal");
  const paymentBankTotal = document.getElementById("paymentBankTotal");
  const paymentDiscTotal = document.getElementById("paymentDiscTotal");

  if (!generateBtn || !startInput || !endInput || !tbody) return;

  const formatAmount = (value, allowZero = false) => {
    const num = Number(value || 0);
    if (!allowZero && num === 0) return "";
    return num.toFixed(2);
  };

  const setTotals = (totals) => {
    receiptCashTotal.textContent = formatAmount(totals.receiptCash, true);
    receiptBankTotal.textContent = formatAmount(totals.receiptBank, true);
    receiptDiscTotal.textContent = formatAmount(totals.receiptDisc, true);
    paymentCashTotal.textContent = formatAmount(totals.paymentCash, true);
    paymentBankTotal.textContent = formatAmount(totals.paymentBank, true);
    paymentDiscTotal.textContent = formatAmount(totals.paymentDisc, true);
  };

  const clearTable = (message) => {
    tbody.innerHTML = "";
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 12;
    cell.className = "cashbook-empty";
    cell.textContent = message;
    row.appendChild(cell);
    tbody.appendChild(row);
  };

  const buildCell = (value) => {
    const cell = document.createElement("td");
    cell.textContent = value || "";
    return cell;
  };

  const renderRows = (receipts, payments) => {
    tbody.innerHTML = "";

    if (!receipts.length && !payments.length) {
      clearTable("No records found for the selected dates.");
      return;
    }

    const maxRows = Math.max(receipts.length, payments.length);
    for (let i = 0; i < maxRows; i += 1) {
      const receipt = receipts[i] || {};
      const payment = payments[i] || {};
      const row = document.createElement("tr");

      row.appendChild(buildCell(receipt.date));
      row.appendChild(buildCell(receipt.description));
      row.appendChild(buildCell(receipt.ref));
      row.appendChild(buildCell(formatAmount(receipt.cash)));
      row.appendChild(buildCell(formatAmount(receipt.bank)));
      row.appendChild(buildCell(formatAmount(receipt.discount)));

      row.appendChild(buildCell(payment.date));
      row.appendChild(buildCell(payment.description));
      row.appendChild(buildCell(payment.ref));
      row.appendChild(buildCell(formatAmount(payment.cash)));
      row.appendChild(buildCell(formatAmount(payment.bank)));
      row.appendChild(buildCell(formatAmount(payment.discount)));

      tbody.appendChild(row);
    }
  };

  const sumField = (items, field) =>
    items.reduce((total, item) => total + Number(item[field] || 0), 0);

  const updateTotals = (receipts, payments) => {
    setTotals({
      receiptCash: sumField(receipts, "cash"),
      receiptBank: sumField(receipts, "bank"),
      receiptDisc: sumField(receipts, "discount"),
      paymentCash: sumField(payments, "cash"),
      paymentBank: sumField(payments, "bank"),
      paymentDisc: sumField(payments, "discount"),
    });
  };

  const updateRangeLabel = (start, end) => {
    rangeEl.textContent = `Cash Book for ${start} to ${end}`;
  };

  generateBtn.addEventListener("click", async () => {
    const startDate = startInput.value;
    const endDate = endInput.value;
    errorEl.textContent = "";

    if (!startDate || !endDate) {
      errorEl.textContent = "Please select both start and end dates.";
      clearTable("Select a date range to generate the cash book.");
      setTotals({
        receiptCash: 0,
        receiptBank: 0,
        receiptDisc: 0,
        paymentCash: 0,
        paymentBank: 0,
        paymentDisc: 0,
      });
      return;
    }

    try {
      const response = await fetch(
        `/api/cashbook/?start_date=${startDate}&end_date=${endDate}`
      );
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.error || "Unable to fetch cashbook data.");
      }
      const data = await response.json();
      const receipts = data.receipts || [];
      const payments = data.payments || [];
      renderRows(receipts, payments);
      updateTotals(receipts, payments);
      updateRangeLabel(startDate, endDate);
    } catch (err) {
      errorEl.textContent = err.message || "Unable to fetch cashbook data.";
      clearTable("No data available.");
    }
  });

  printBtn.addEventListener("click", () => {
    window.print();
  });
})();
