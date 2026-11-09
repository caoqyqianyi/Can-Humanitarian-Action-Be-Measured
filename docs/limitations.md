# Limitations

Written down because a tool that overstates what it knows is worse than no tool.

## The administrative-boundary gap

Both gridded indicators in the registry — flood exposure and crop-yield
anomaly — are open, licensed and verified in the ISIMIP catalogue, and both
stop one step short of a national indicator. Turning a 300 arcsec grid into
"people in Bangladesh exposed to 1-in-100-year flooding" needs an
administrative boundary raster, population weighting per cell, and a decision
about the depth threshold that counts as exposure. None of that is in this
repository. The registry therefore records them as `partial`, and the audit
reports them as conditional rather than claiming a number it has not computed.

That gap is the single most valuable next piece of work: point-in-polygon
aggregation against a boundary layer, with the threshold made an explicit
parameter rather than a hidden constant.

## Model spread

ISIMIP provides multiple impact models per variable. A single model's crop
anomaly is not a trigger-grade signal; the spread between models is the
information. Any use as an anticipatory-action trigger needs an ensemble
threshold, not one model's output.

## Denominators are not needs

The population series gives the size of the denominator. It says nothing about
how many of those people need assistance, which is a needs-assessment question.
A rising denominator mechanically dilutes any "share of population reached"
indicator — which is the point of the baseline-drift table, and also the
reason denominators should never be presented as need.

## Vintage

The series ends in 2020. For a programme running to 2028 this is a stale
denominator, and the population series should be replaced by the current
national projection before any per-capita indicator is reported. The code
reads whichever series is placed in `data/reference/`; swapping it is a
one-file change, and the registry note should be updated with it.

## The audit tests availability, not validity

An indicator can pass every check and still be a poor measure of its result
statement. Five checks about data existence do not substitute for technical
review of whether a food-consumption score measures food security in this
context.

## The example framework is synthetic

`data/examples/logframe_example.csv` is written to exercise every failure mode,
not to describe a real proposal. It should not be cited as an example of
practice.

## Boundaries are cartographic, not authoritative

The map in the brief draws Natural Earth 110m geometry. That is adequate to
place a denominator series and entirely inadequate as a published boundary
representation: disputed and de facto lines follow Natural Earth's own
depiction, and the simplification fills lakes and merges small islands.

For internal analysis this does not matter. For anything that leaves the
building it does — boundary representation is politically sensitive in most
of the contexts this tool is built for, and an agency's own reference layer
governs, not a public-domain one. Redrawing on that layer is a substitution,
not a redesign: `mapview.load_features()` reads one file.

The choropleth also colours *states*, while the series counts *national units*
— 238 of them, including dependencies the map draws inside another country.
The coverage line in the brief ("172 of the 176 countries drawn") is computed
at render time so the gap is stated rather than glossed.
