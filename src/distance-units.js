export const KM_PER_MILE = 1.609344

export function distanceLabel(km, units, decimals = 1) {
  const value = units === 'mi' ? km / KM_PER_MILE : km
  return `${Number(value.toFixed(decimals))} ${units === 'mi' ? 'mi' : 'km'}`
}

export function distanceText(text, units) {
  return String(text).replace(/\b(\d+(?:\.\d+)?)\s*km\b/g, (_, km) => distanceLabel(Number(km), units, 2))
}

export function distanceRings(units) {
  return [10, 5, 2, 1].map(value => ({
    km: value * (units === 'mi' ? KM_PER_MILE : 1),
    label: `${value} ${units === 'mi' ? 'mi' : 'km'}`,
  }))
}
