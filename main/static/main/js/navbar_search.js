document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("globalSearchForm");
    const input = document.getElementById("globalSearchInput");
    const suggestionsBox = document.getElementById("searchSuggestions");

    if (!form || !input || !suggestionsBox) {
        return;
    }

    const suggestUrl = input.dataset.suggestUrl;
    const MAX_VISIBLE_SUGGESTIONS = 10;
    const MAX_CACHE_ENTRIES = 25;
    const MAX_RECENT_SEARCHES = 5;
    const RECENT_STORAGE_KEY = "ledgerpro_recent_searches";

    const suggestionCache = new Map();

    let debounceTimer = null;
    let activeController = null;
    let activeIndex = -1;
    let currentItems = [];
    let recentSearches = loadRecentSearches();

    function loadRecentSearches() {
        try {
            const raw = window.localStorage.getItem(RECENT_STORAGE_KEY);
            const parsed = raw ? JSON.parse(raw) : [];
            if (!Array.isArray(parsed)) {
                return [];
            }
            return parsed
                .map(function (value) {
                    return String(value || "").trim();
                })
                .filter(Boolean)
                .slice(0, MAX_RECENT_SEARCHES);
        } catch (_error) {
            return [];
        }
    }

    function saveRecentSearches() {
        try {
            window.localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(recentSearches));
        } catch (_error) {
            // Ignore storage failures (private mode / quota limits).
        }
    }

    function addRecentSearch(term) {
        const clean = (term || "").trim();
        if (!clean) {
            return;
        }

        recentSearches = [clean].concat(
            recentSearches.filter(function (item) {
                return item.toLowerCase() !== clean.toLowerCase();
            })
        ).slice(0, MAX_RECENT_SEARCHES);

        saveRecentSearches();
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function escapeRegExp(value) {
        return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function highlightLabel(label, query) {
        const cleanLabel = String(label || "");
        const cleanQuery = String(query || "").trim();

        if (!cleanQuery) {
            return escapeHtml(cleanLabel);
        }

        const parts = cleanLabel.split(new RegExp("(" + escapeRegExp(cleanQuery) + ")", "ig"));
        return parts
            .map(function (part) {
                if (part.toLowerCase() === cleanQuery.toLowerCase()) {
                    return "<mark>" + escapeHtml(part) + "</mark>";
                }
                return escapeHtml(part);
            })
            .join("");
    }

    function setExpanded(isExpanded) {
        input.setAttribute("aria-expanded", isExpanded ? "true" : "false");
    }

    function hideSuggestions() {
        suggestionsBox.hidden = true;
        suggestionsBox.innerHTML = "";
        currentItems = [];
        activeIndex = -1;
        input.removeAttribute("aria-activedescendant");
        setExpanded(false);
    }

    function setActiveIndex(nextIndex) {
        if (!currentItems.length) {
            activeIndex = -1;
            input.removeAttribute("aria-activedescendant");
            return;
        }

        if (nextIndex < 0) {
            nextIndex = currentItems.length - 1;
        }
        if (nextIndex >= currentItems.length) {
            nextIndex = 0;
        }

        activeIndex = nextIndex;

        const options = suggestionsBox.querySelectorAll(".search-suggestion-item");
        options.forEach(function (option, index) {
            const isActive = index === activeIndex;
            option.classList.toggle("is-active", isActive);
            option.setAttribute("aria-selected", isActive ? "true" : "false");
            if (isActive) {
                input.setAttribute("aria-activedescendant", option.id);
                option.scrollIntoView({ block: "nearest" });
            }
        });
    }

    function mergeWithRecent(apiItems, query) {
        const merged = [];
        const seen = new Set();
        const cleanQuery = (query || "").trim().toLowerCase();

        function append(item) {
            if (!item) {
                return;
            }
            const value = String(item.value || item.label || "").trim();
            if (!value) {
                return;
            }
            const key = value.toLowerCase();
            if (seen.has(key)) {
                return;
            }
            seen.add(key);
            merged.push({
                value: value,
                label: String(item.label || value),
                type: item.type || "Match"
            });
        }

        (apiItems || []).forEach(append);

        recentSearches
            .filter(function (item) {
                return !cleanQuery || item.toLowerCase().includes(cleanQuery);
            })
            .forEach(function (item) {
                append({ value: item, label: item, type: "Recent" });
            });

        return merged.slice(0, MAX_VISIBLE_SUGGESTIONS);
    }

    function renderSuggestions(items, query) {
        if (!Array.isArray(items) || items.length === 0) {
            hideSuggestions();
            return;
        }

        currentItems = items;
        activeIndex = -1;
        input.removeAttribute("aria-activedescendant");
        suggestionsBox.innerHTML = "";

        items.forEach(function (item, index) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "search-suggestion-item";
            button.id = "search-suggestion-" + index;
            button.setAttribute("role", "option");
            button.setAttribute("aria-selected", "false");
            button.dataset.index = String(index);

            const label = document.createElement("span");
            label.className = "search-suggestion-label";
            label.innerHTML = highlightLabel(item.label || item.value || "", query);

            const type = document.createElement("small");
            type.className = "search-suggestion-type";
            type.textContent = item.type || "Match";

            button.appendChild(label);
            button.appendChild(type);
            suggestionsBox.appendChild(button);
        });

        suggestionsBox.hidden = false;
        setExpanded(true);
    }

    function setCache(key, items) {
        if (suggestionCache.has(key)) {
            suggestionCache.delete(key);
        }
        suggestionCache.set(key, items);

        if (suggestionCache.size > MAX_CACHE_ENTRIES) {
            const oldestKey = suggestionCache.keys().next().value;
            suggestionCache.delete(oldestKey);
        }
    }

    function fetchSuggestions(rawQuery) {
        const query = (rawQuery || "").trim();

        if (!query) {
            const onlyRecent = mergeWithRecent([], "");
            renderSuggestions(onlyRecent, "");
            return;
        }

        if (!suggestUrl) {
            hideSuggestions();
            return;
        }

        const cacheKey = query.toLowerCase();
        if (suggestionCache.has(cacheKey)) {
            renderSuggestions(mergeWithRecent(suggestionCache.get(cacheKey), query), query);
            return;
        }

        if (activeController) {
            activeController.abort();
        }

        activeController = new AbortController();

        fetch(suggestUrl + "?q=" + encodeURIComponent(query), {
            method: "GET",
            headers: { Accept: "application/json" },
            signal: activeController.signal
        })
            .then(function (response) {
                if (!response.ok) {
                    return { suggestions: [] };
                }
                return response.json();
            })
            .then(function (payload) {
                const apiSuggestions = Array.isArray(payload.suggestions) ? payload.suggestions : [];
                setCache(cacheKey, apiSuggestions);
                renderSuggestions(mergeWithRecent(apiSuggestions, query), query);
            })
            .catch(function (error) {
                if (error && error.name === "AbortError") {
                    return;
                }
                hideSuggestions();
            });
    }

    function selectSuggestionByIndex(index, submitAfterSelect) {
        const item = currentItems[index];
        if (!item) {
            return;
        }

        input.value = item.value || item.label || "";
        hideSuggestions();
        input.focus();

        if (submitAfterSelect) {
            addRecentSearch(input.value);
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
            } else {
                form.submit();
            }
        }
    }

    input.addEventListener("input", function () {
        const query = input.value.trim();
        clearTimeout(debounceTimer);

        debounceTimer = setTimeout(function () {
            fetchSuggestions(query);
        }, 300);
    });

    input.addEventListener("focus", function () {
        fetchSuggestions(input.value.trim());
    });

    input.addEventListener("keydown", function (event) {
        const hasVisibleItems = !suggestionsBox.hidden && currentItems.length > 0;

        if (event.key === "Escape") {
            hideSuggestions();
            return;
        }

        if (event.key === "ArrowDown") {
            event.preventDefault();
            if (!hasVisibleItems) {
                fetchSuggestions(input.value.trim());
                return;
            }
            setActiveIndex(activeIndex + 1);
            return;
        }

        if (event.key === "ArrowUp" && hasVisibleItems) {
            event.preventDefault();
            setActiveIndex(activeIndex - 1);
            return;
        }

        if (event.key === "Enter" && hasVisibleItems && activeIndex >= 0) {
            event.preventDefault();
            selectSuggestionByIndex(activeIndex, true);
        }
    });

    suggestionsBox.addEventListener("mousemove", function (event) {
        const target = event.target.closest(".search-suggestion-item");
        if (!target) {
            return;
        }
        const index = Number(target.dataset.index);
        if (!Number.isNaN(index) && index !== activeIndex) {
            setActiveIndex(index);
        }
    });

    suggestionsBox.addEventListener("click", function (event) {
        const target = event.target.closest(".search-suggestion-item");
        if (!target) {
            return;
        }
        const index = Number(target.dataset.index);
        if (!Number.isNaN(index)) {
            selectSuggestionByIndex(index, false);
        }
    });

    document.addEventListener("click", function (event) {
        if (!form.contains(event.target)) {
            hideSuggestions();
        }
    });

    form.addEventListener("submit", function () {
        addRecentSearch(input.value);
        hideSuggestions();
    });
});
