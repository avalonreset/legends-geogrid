// A small JSON Schema checker for the keywords the viewer schemas use (draft 2020-12 subset).
// It resolves local "$ref" pointers against the schema it was created for.
export function createValidator(schema) {
  const resolve = ref => ref.split('/').slice(1).reduce((node, key) => node[key], schema)
  const kind = v => (v === null ? 'null' : Array.isArray(v) ? 'array' : Number.isInteger(v) ? 'integer' : typeof v)
  function validate(value, node, path = '$') {
    if (node.$ref) return validate(value, resolve(node.$ref), path)
    const errors = []
    if (node.oneOf && !node.oneOf.some(option => validate(value, option, path).length === 0)) return [`${path}: matches no oneOf option`]
    if ('const' in node && value !== node.const) errors.push(`${path}: expected ${node.const}`)
    if (node.enum && !node.enum.includes(value)) errors.push(`${path}: not one of ${node.enum.join(', ')}`)
    if (node.type) {
      const types = [].concat(node.type)
      if (!types.some(t => t === kind(value) || (t === 'number' && kind(value) === 'integer'))) return [...errors, `${path}: expected ${types.join('|')}, got ${kind(value)}`]
    }
    if (typeof value === 'number') {
      if ('minimum' in node && value < node.minimum) errors.push(`${path}: below minimum`)
      if ('maximum' in node && value > node.maximum) errors.push(`${path}: above maximum`)
    }
    if (typeof value === 'string' && 'minLength' in node && value.length < node.minLength) errors.push(`${path}: too short`)
    if (Array.isArray(value)) {
      if ('minItems' in node && value.length < node.minItems) errors.push(`${path}: too few items`)
      if (node.items) value.forEach((item, i) => errors.push(...validate(item, node.items, `${path}[${i}]`)))
    }
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const key of node.required || []) if (!(key in value)) errors.push(`${path}: missing ${key}`)
      for (const [key, child] of Object.entries(node.properties || {})) if (key in value) errors.push(...validate(value[key], child, `${path}.${key}`))
      if (node.additionalProperties && typeof node.additionalProperties === 'object') {
        for (const [key, child] of Object.entries(value)) if (!(key in (node.properties || {}))) errors.push(...validate(child, node.additionalProperties, `${path}.${key}`))
      }
    }
    return errors
  }
  return value => validate(value, schema)
}
