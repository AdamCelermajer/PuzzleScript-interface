"use strict";

class PriorityQueue {
  constructor(compare) {
    this.items = [];
    this.compare = compare;
  }

  get size() {
    return this.items.length;
  }

  peek() {
    return this.items[0] ?? null;
  }

  push(value) {
    const index = this.items.length;
    this.items.push(value);
    this._bubbleUp(index);
  }

  pop() {
    if (this.items.length === 0) return null;
    const first = this.items[0];
    const last = this.items.pop();
    if (this.items.length > 0) {
      this.items[0] = last;
      this._bubbleDown(0);
    }
    return first;
  }

  _bubbleUp(startIndex) {
    let index = startIndex;
    while (index > 0) {
      const parent = Math.floor((index - 1) / 2);
      if (this.compare(this.items[parent], this.items[index]) <= 0) break;
      [this.items[parent], this.items[index]] = [
        this.items[index],
        this.items[parent],
      ];
      index = parent;
    }
  }

  _bubbleDown(startIndex) {
    let index = startIndex;
    while (true) {
      const left = (index * 2) + 1;
      const right = left + 1;
      let best = index;
      if (
        left < this.items.length
        && this.compare(this.items[left], this.items[best]) < 0
      ) {
        best = left;
      }
      if (
        right < this.items.length
        && this.compare(this.items[right], this.items[best]) < 0
      ) {
        best = right;
      }
      if (best === index) break;
      [this.items[index], this.items[best]] = [
        this.items[best],
        this.items[index],
      ];
      index = best;
    }
  }
}

module.exports = { PriorityQueue };
