export const KM_PER_MILE = 1.609344

export function distanceLabel(km, units, decimals = 1) {
  const value = units === 'mi' ? km / KM_PER_MILE : km
  return `${Number(value.toFixed(decimals))} ${units === 'mi' ? 'mi' : 'km'}`
}

export function distanceText(text, units) {
  return String(text).replace(/\b(\d+(?:\.\d+)?)\s*km\b/g, (_, km) => distanceLabel(Number(km), units, 2))
}

export function distanceRings(units, maxKm = null) {
  const factor = units === 'mi' ? KM_PER_MILE : 1
  const steps = maxKm && maxKm > 10 * factor ? [50, 40, 30, 20, 15, 10, 5, 2, 1] : [10, 5, 2, 1]
  return steps.map(value => ({
    km: value * factor,
    label: `${value} ${units === 'mi' ? 'mi' : 'km'}`,
  }))
}
