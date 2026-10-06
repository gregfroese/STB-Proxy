// Saved filters: a dropdown to apply one, Save to keep the current filters under a name,
// Delete to remove the chosen one. Kept on the server (config.json), so every browser sees them.
//   page      "editor" or "guide"
//   container element to put the controls in
//   getState  function returning the page's current filters (a plain object)
//   setState  function applying a saved object
function setUpSavedFilters(page, container, getState, setState) {
    container.innerHTML =
        '<select class="form-select form-select-sm me-1" style="width: auto;" title="Apply saved filters"></select>' +
        '<button type="button" class="btn btn-sm btn-outline-light me-1" title="Save these filters under a name">Save</button>' +
        '<button type="button" class="btn btn-sm btn-outline-danger" title="Delete the chosen saved filters">Delete</button>';
    var select = container.querySelector("select");
    var buttons = container.querySelectorAll("button");
    var saved = {};

    function render(chosen) {
        select.innerHTML = "";
        var first = document.createElement("option");
        first.value = "";
        first.textContent = Object.keys(saved).length ? "Saved filters..." : "No saved filters";
        select.appendChild(first);
        Object.keys(saved).sort(function (a, b) { return a.localeCompare(b); }).forEach(function (name) {
            var option = document.createElement("option");
            option.value = name;
            option.textContent = name;
            select.appendChild(option);
        });
        select.value = chosen && saved[chosen] ? chosen : "";
        buttons[1].disabled = !select.value;
    }

    function post(body) {
        return fetch("/filters/" + page, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        }).then(function (r) {
            if (!r.ok) {
                throw new Error("Couldn't save");
            }
            return r.json();
        });
    }

    select.addEventListener("change", function () {
        buttons[1].disabled = !select.value;
        if (select.value && saved[select.value]) {
            setState(saved[select.value]);
        }
    });

    buttons[0].addEventListener("click", function () {
        var name = window.prompt("Name for these filters:", select.value || "");
        if (!name || !name.trim()) {
            return;
        }
        name = name.trim();
        post({ name: name, filters: getState() })
            .then(function (all) { saved = all; render(name); })
            .catch(function () { alert("Couldn't save the filters. Try again."); });
    });

    buttons[1].addEventListener("click", function () {
        var name = select.value;
        if (!name || !window.confirm('Delete the saved filters "' + name + '"?')) {
            return;
        }
        post({ name: name, filters: {}, delete: true })
            .then(function (all) { saved = all; render(""); })
            .catch(function () { alert("Couldn't delete the filters. Try again."); });
    });

    fetch("/filters/" + page)
        .then(function (r) { return r.json(); })
        .then(function (all) { saved = all; render(""); });
}
