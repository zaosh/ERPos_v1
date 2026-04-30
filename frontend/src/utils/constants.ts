export const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const ITEM_CATEGORIES = [
  'tshirt', 'pants', 'jacket', 'dress', 'skirt',
  'shorts', 'sweater', 'hoodie', 'other',
] as const

export const ITEM_TYPES = [
  'plain', 'graphic', 'patterned', 'striped', 'band',
  'anime', 'sports', 'vintage_graphic', 'holiday', 'branded',
  'statement', 'unknown',
] as const

export const ITEM_CONDITIONS = ['excellent', 'good', 'fair', 'worn'] as const

export const ITEM_STATUSES = ['in_stock', 'sold', 'reserved', 'archived'] as const

export const PAYMENT_TYPES = ['cash', 'card', 'other'] as const

export const ANALYTICS_PERIODS = ['7d', '30d', '90d'] as const

export const DEAD_STOCK_DAYS_DEFAULT = 21

export type ItemCategory = typeof ITEM_CATEGORIES[number]
export type ItemType = typeof ITEM_TYPES[number]
export type ItemCondition = typeof ITEM_CONDITIONS[number]
export type ItemStatus = typeof ITEM_STATUSES[number]
export type PaymentType = typeof PAYMENT_TYPES[number]
export type AnalyticsPeriod = typeof ANALYTICS_PERIODS[number]
