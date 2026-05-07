const _fmt = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
})

export const money = (n: number | string) => _fmt.format(typeof n === 'string' ? parseFloat(n) : n)
