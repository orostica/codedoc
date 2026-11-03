import type { Item } from "./types";

export async function loadItems(): Promise<Item[]> {
  const response = await fetch("https://api.example.invalid/api/items", {
    method: "GET"
  });
  return response.json();
}
