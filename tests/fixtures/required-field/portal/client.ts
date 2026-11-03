type PersonInput = { name?: string; age: number };

export async function createPerson(input: PersonInput) {
  return fetch("https://api.example.invalid/api/people", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ age: 18 })
  });
}
