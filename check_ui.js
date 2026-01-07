const { TableUI } = require('puzzlescript');

console.log("TableUI methods:");
console.log(Object.getOwnPropertyNames(TableUI.prototype));

try {
    const ui = new TableUI();
    console.log("Instance methods:");
    console.log(Object.getPrototypeOf(ui));
} catch (e) {
    console.log("Could not instantiate args", e.message);
}
