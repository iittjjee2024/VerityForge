// Renders the product list into the page.
export async function loadProducts() {
  const res = await fetch("/api/products");
  const products = await res.json();
  return products.map((p) => `${p.name}: $${p.price}`);
}
