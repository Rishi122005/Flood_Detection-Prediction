# Dataset inventory

This checkout contains Sen1Floods11 hand-labeled samples under `data/`, along with benchmark split IDs under `splits/`. The local `S1GRDHand` and `LabelHand` directories contain 446 files each. The broader data folders also include `S1OtsuLabelHand`, `JRCWaterHand`, `S2L1CHand`, and `CopernicusDEM` products.

## SAR and label layout

SAR scenes are GeoTIFFs with two bands: VV followed by VH. The paired hand-label filename uses the same scene ID with `_LabelHand.tif`; labels use `-1` for unknown, `0` for non-flood, and `1` for flood. The model expects 512×512×2 inputs. Existing SAR rasters carry CRS and affine transforms; the local benchmark samples inspected use geographic coordinates and 512×512 dimensions.

## Split lists

The supplied split files contain 252 training IDs, 89 validation IDs, and 90 test IDs. There are 14 India IDs in each of validation and test, and 40 in training. Pairing is checked against actual files at runtime rather than assuming every split entry has every modality.

## India subset and geographic scope

Inference discovery finds a case-insensitive `India` token in scene filenames under `data/S1GRDHand`, then verifies the file is a readable two-band raster. It found 68 compatible scenes in this checkout. The official India test subset consists of 14 scenes and is the only India label-based test evaluation reported in this project. This is not nationwide or event-specific India coverage. Filenames provide the India region label; they do not, by themselves, establish a city, event date, or flood occurrence.

The local `data/vijayawada_sar/` directory is empty. No Vijayawada September 2024 SAR scene or India event-specific prediction should be claimed from that directory.

## Data provenance and scope

The repository includes `Sen1Floods11_Metadata.geojson`, the benchmark data folders, and split ID files. No external dataset download is required for the supported local workflow. See the project reference in the root README and the dataset metadata supplied with this checkout.
