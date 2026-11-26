import bundledSample from './data/cosmis-deli-philly-study.json'
import bundledResearch from './data/cosmis-deli-philly-campaign-research.json'
import bundledNameReview from './data/cosmis-deli-philly-name-review.json'

const bootstrap = globalThis.__GEOGRID_BOOTSTRAP__
export const sample = bootstrap?.study || bundledSample
export const sampleResearch = bootstrap?.campaignResearch !== undefined ? bootstrap.campaignResearch : bundledResearch
export const sampleNameReview = bootstrap?.nameReview !== undefined ? bootstrap.nameReview : bundledNameReview
