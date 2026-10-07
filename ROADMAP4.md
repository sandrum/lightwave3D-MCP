# Roadmap 4: what's left (draft)

ROADMAP.md, ROADMAP2.md and ROADMAP3.md are all done, apart from the open
items listed below. This roadmap is the full picture of everything left.
It's built from a pass over every command in
`lwcommandport/layout/__init__.py` (823 Layout commands) and
`lwcommandport/modeler/__init__.py` (62 Modeler commands).

Each Layout command was checked against `server.py` and the docs:

| | Layout commands |
|---|---|
| Wrapped by a tool | 162 |
| Investigated (in PLAN/ROADMAP docs) but not wrapped | 45 |
| Not looked at yet | 616 |

Every command can already be sent through `lw_run_command`. What a
dedicated tool adds is a confirmed argument format, a read-back where
the SDK has one, and refusal of inputs that pop modal dialogs. The
stub's signatures have been wrong often enough (`MotionBlur`,
`NoiseFilter`, the `ColorSpace*` family) that each one still needs a
Cmd History check.

## How each item gets done

- **One branch per category.** Start from an up-to-date `main`, and
  fast-forward the branch into `main` once the work is live-verified
  and CI passes.
- **Unit tests for every new tool** in `tests/unit/`, run against the
  stand-ins (`fake_layout`, `fake_query`, `tests/fake_lwsdk.py`). They
  test the tool's own logic: argument mapping, label translation,
  refusals that send nothing, and read-back parsing.
- **Existing tests keep passing unchanged.** If a change seems to need
  an old test edited, that means the old behaviour changed, so it gets
  flagged rather than quietly adjusted.
- **Live check in Layout before merging**, with Cmd History as the
  reference for argument formats.

## Open items carried over

- **Envelope on an unanimated node input** (ROADMAP3 #11 follow-up).
  `AddEnvelope`/`RemoveEnvelope` are in the untouched list below and
  are the first thing to try.
- **Dynamics survey** (ROADMAP3 "Not investigated this pass"). The full
  command list has no HardFX/SoftFX/ParticleFX commands. Those are
  plug-ins, so the route to them would be the server commands under
  Plug-ins below (`ApplyServerByItemID` etc.), not a command family of
  their own.
- **#4 UI freeze**: only worth chasing if it happens again.
- **`RenderMode(renderintegrator)`**: nothing in the UI to check it against.
- **Reconstruction filter**: read-only. It's a per-buffer setting that
  logs no command.
- **`CreateContentPath`/`RecentContentDirs`**: they look like one-shot
  UI actions, so they're left unwrapped.
- **Modeler reads**: paused. Reading saved `.lwo` files from disk is the
  known substitute.

## Untouched Layout commands, by category

Ranked roughly by how much they'd add.

### 1. Render output - high value
Lets a render actually land in a file of your choosing, which the
render tools don't control yet.
`SaveRGB`, `SaveRGBPrefix`, `SaveRGBServer`, `SaveAlpha`,
`SaveAlphaPrefix`, `SaveAlphaServer`, `SaveAnimation`,
`SaveAnimationName`, `SaveAnimationServer`, `UnPreMultiplyAlpha`,
`MultilayerEnabled`, `MultilayerUseOutputPath`, `MultilayerPath`,
`MultilayerFilename`, `AddCustomBuffer`, `RemoveCustomBuffer`,
`LoadRenderSettings`, `SaveRenderSettings`, `SaveRenderPreset`,
`SaveBufferSet`, `SaveBufferSetPreset`, `LoadBufferSet`,
`SyncBufferSet`, `RenderSelected`, `AutoFrameAdvance`.

### 2. Item management and selection - high value
Basic scene editing that currently needs `lw_run_command` and guesswork.
- Create: `AddCamera`, `AddDistantLight`, `AddSpotlight`,
  `AddLinearLight`, `AddAreaLight`, `Clone`, `Mirror`,
  `ReplaceWithObject`, `ReplaceObjectLayer`, `ReplaceWithNull`.
- Change light type: `DistantLight`, `PointLight`, `Spotlight`,
  `LinearLight`, `AreaLight`, `CustomLight`.
- Rename: `Rename`, `RenameLayer`, `RenameLayerID`.
- Select: `SelectByName`, `SelectByPartialName`, `SelectParent`,
  `SelectChild`, `PreviousSibling`, `NextSibling`, `FirstItem`,
  `LastItem`, `PreviousItem`, `NextItem`, `ClearSelected`,
  `SelectAllObjects`, `SelectAllLights`, `SelectAllCameras`,
  `SelectAllBones`, `EnableFromSelection`, `DisableFromSelection`.
- Delete: `ClearAllObjects`, `ClearAllLights`, `ClearAllCameras`,
  `ClearAllBones`.
- Per-item state: `ItemActive`, `ItemLock`, `ItemUnlock`,
  `ItemVisibility`, `ItemColor`, `ItemShowChildren`,
  `ItemShowChannels`, `ItemIconScale`, `ObjectMeshGroup`.

### 3. Animation and motion - high value
- Keys and envelopes: `DeleteKey`, `AutoKey`, `AutoKeyFixedFrame`,
  `SetTCB`, `AddEnvelope`, `RemoveEnvelope`, `AddRotation`, `AddScale`.
- Transport: `GoToFirstFrame`, `GoToLastFrame`, `PreviousFrame`,
  `NextFrame`, `PreviousKey`, `NextKey`, `FrameStep`.
- Absolute transforms: `PositionItem`, `PositionItemWorld`,
  `RotationItem`, `RotationItemWorld`, `ScaleItem`, `ScaleItemWorld`,
  plus the `*BlendMethod`/`*Blend` variants.
- Pivots: `PivotPosition`, `PivotRotation`, `RecordPivotRotation`.
- Motion files: `LoadMotion`, `SaveMotion`.
- Paths: `SplineItem`, `ClosedSpline`, `FlipSideSpline`, `SplineFit`,
  `PathAlignLookAhead`, `PathAlignMaxLookSteps`, `PathAlignReliableDist`.
- Per-channel limits and IK (9 channels each: X Y Z H P B SX SY SZ):
  `*Controller`, `*Limits`, `Limit*`, `*Stiffness`, `*Transform`,
  `*Follow`, and `RecordMin/MaxPosition/Angles/Scale` - about 60
  commands, all one pattern. Worth one tool.
- Scene timing: `FramesPerSecond`, `FractionalFrames`,
  `DefaultSceneLength`, `DefaultStartFrame`, `ParentInPlace`.

### 4. Object properties - medium-high
`SubPatchLevel`, `SubdivisionOrder`, `SubPatchUV`, `MatteObject`,
`MatteColor`, `ObjectDissolve`, `DistanceDissolve`,
`MaxDissolveDistance`, `CastShadow`, `ReceiveShadow`, `SelfShadow`,
`ShadowOffset`, `BumpDisplacement`, `BumpDisplacementDistance`,
`BumpDisplacementOrder`, `DisplacementMapOrder`, `PolygonSize`,
`ParticleThickness`, `LineThickness`, `FogLevel`, `PolygonEdgeFlags`,
`PolygonEdgeThickness`, `PolygonEdgeColor`, `PolygonEdgeZScale`,
`ShadeEdges`, `ShrinkEdgesWithDistance`, `ShrinkEdgesNominalDistance`,
`MorphSurfaces`, `MorphMTSE`, `MetaballResolution`, `AddPartigon`,
`CalculateAllNormals`, `RenderLines`, `RenderInstances`.

### 5. Light properties - medium-high
- Shadows: `ShadowType`, `ShadowColor`, `ShadowMapSize`,
  `ShadowMapFuzziness`, `ShadowMapFitCone`, `ShadowMapAngle`,
  `CacheShadowMap`, `ShadowExclusion`.
- Other: `AffectDiffuse`, `AffectSpecular`, `AffectOpenGL`,
  `LightEdgeAngle`, `ProjectionImage`, `VolumetricLighting`,
  `DoubleSidedAreaLights`, `LightBufferGroup`,
  `SelectLightBufferGroupMembers`, `SaveLight`.
- Light nodes: `LightUseNodes`, `LightLoadNodes`, `LightSaveNodes`.
  The node tools work on surfaces only, so this could extend them to lights.
- Lens flares: `EnableLensFlares`, `LensFlare`, `FlareOptions`,
  `SetFlareIntensity` and about 30 more `Flare*` commands. They're a
  self-contained block, and lower priority.

### 6. Camera properties - medium
`FocalDistance`, `DiaphragmSides`, `DiaphragmRotation`,
`ResolutionPreset`, `ResolutionMultiplier`, `PixelAspect`,
`FilmHeight`, `OverscanMode`, `OverscanSize`, `LimitedRegion`,
`RegionPosition`, `FieldRendering`, `MotionBlurSubFrames`,
`MotionBlurPasses`, `ParticleBlur`, `BlurLength`, `NoiseSampler`,
`EnhancedAA`, `SoftFilter`, `Stereoscopic`, `EyeSeparation`,
`UseConvergencePoint`, `ConvergencePoint`, `ConvergenceToeIn`.

### 7. Global render settings - medium
`RayTraceTransparency`, `RayTraceOcclusion`, `RayCutoff`,
`LightSamples`, `AmbientOcclusionShadows`, `AmbientOcclusionRange`,
`UseZMinimumMaximum`, `ZBufferMinimum`, `ZBufferMaximum`,
`DepthBufferAA`, `LimitDynamicRange`, `LimitDynamicRangeMin`,
`LimitDynamicRangeMax`, `DefaultDitherIntensity`, `DitherIntensity`,
`HDRFilter`, `CacheRadiosity`, `EnableMipMapping`, `PixelFiltersMT`,
`ImageProcessing`, `UseBackgroundColor`, `BackgroundColor`,
`GroundSqueezeColor`.

### 8. Scene and object file I/O - medium
`SaveSceneCopy`, `RevertScene`, `LoadFromScene`,
`LoadElementsFromScene`, `SaveAllObjects`, `SaveObjectCopy`,
`ExportLWO2`, `SaveFrozenLwo`, `SaveTransformed`, `SaveWavefrontObj`,
`SaveTransformedWavefrontObj`, `SaveFrozenWavefrontObj`, the `OBJ*`
export options (13), the old-format `SaveLWSC*` variants (9),
`LoadAudio`, `ClearAudio`.

### 9. Plug-ins and servers - medium, riskier
This is the way into displacement/motion modifiers, image filters,
pixel filters and probably the dynamics plug-ins. Plug-in UIs can pop
dialogs, so it needs careful staging.
`ApplyServerByItemID`, `RemoveServer`, `RemoveServerByItemID`,
`EditServer`, `EnableServer`, `EnableServerByItemID`,
`PositionServerByItemID`, `ReorderServerByItemID`,
`SaveServerDataByItemID`, `LoadServerDataByItemID`,
`SetServerDescriptionByItemID`, `AddPlugins`, `ActivateMaster`,
`ActivateMasterUnique`, `RemoveMaster`, `FlushUnusedPlugins`, `Generics`.

### 10. Compositing images - medium
`SetBackgroundImage`, `SetForegroundImage`, `SetForegroundAlphaImage`,
`SyncImageToFrame`, `EnableForegroundFaderAlpha`,
`SetForegroundDissolve`, `EnableForegroundKey`, `SetLowClipColor`,
`SetHighClipColor`, `ChangeClipType`, `LoadClip`.

### 11. Bones extras - medium-low
`SkelegonsToBones`, `BoneSource`, `AddJoint`, `AddChildJoint`,
`FasterBones`, `NumLimitedBones`, `BoneNormalization`,
`AddBoneRestLength`, `BoneMayaStyleDraw`.

### 12. Dialog handling - small but useful
`AutoConfirm` and `AlertLevel` might stop LightWave popping the modal
dialogs that have blocked Layout several times. If one of them works,
it could make several current refusals unnecessary.

### 13. Previews - low
`MakePreview`, `PlayPreview`, `FreePreview`, `LoadPreview`,
`SavePreview`, `PreviewOptions`, `PreviewFirstFrame`,
`PreviewLastFrame`, `PreviewFrameStep`, `PreviewFrameRateScale`.
`MakePreview` producing a saved preview file could be handy, but these
likely open dialogs.

### 14. Preferences - low
`AutoSaveObj`, `AutoSaveScene`, `UseCustomPaths`,
`ImageCacheMaximum`, `ImageCacheEnable`, `MTMeshEval`,
`ProtectLegacyScenes`, `ExportSceneInfo`, `DefaultKeyframe`,
`InitialKeyframePerScene`, `SaveConfig`, `LoadConfig`, `Undo`, `Redo`.
`Undo`/`Redo` stand out: they'd give a safety net for the other tools.

### Not worth wrapping
Viewport and display, about 90 commands: views (`TopView`,
`CameraView`...), zoom/fit, grid, `Show*` overlays, OpenGL options,
`Layout_*Viewport`, `ViewPort*`, `BoneXRay` and similar.

Interactive tools, which need a mouse: `MoveTool`, `RotateTool`,
`SizeTool` and the other `*Tool` commands, plus `ChangeTool`, `Reset`,
`Numeric`.

Panels and windows that only open UI: `SceneEditor*`, `GraphEditor`,
`ImageEditor`, `PreviewWindow`, `Presets`, `StudioPanel`,
`EditMenus`, `EditKeys`, `*_SetWindowPos/Size` and others.

Session and account commands, unsafe or pointless: `Quit`, `About`,
`ReportABug`, `RequestAFeature`, `EnterUnlockCode`, `OnLine`,
`OffLine`, `EnableCommandPort`, `DisableCommandPort`, `Model`,
`Synchronize`, the `Studio*` commands, `OpenPCoreConsole`,
`ClosePCoreConsole`, `PCorePython`.

## Modeler

11 of the 62 Modeler commands are used directly. The remaining 51 are
geometry operations, all reachable through `modeler_run_command`:
- Points: `mergepoints`, `weldpoints`, `weldaverage`, `unweld`.
- Polygons: `splitpols`, `mergepols`, `removepols`, `unifypols`,
  `alignpols`, `triple`, `subdivide`, `smooth`, `jitter`, `smscale`,
  `quantize`, `center`.
- Extrude and clone: `pathextrude`, `pathclone`, `railextrude`,
  `railclone`, `skinpols`, `morphpols`, `axisdrill`, `soliddrill`.
- Surfaces and parts: `changesurface`, `changepart`.
- Patches and curves: `make4patch`, `togglepatches`, `toggleccstart`,
  `toggleccend`, `freezecurves`, `smoothcurves`.
- Editing: `cut`, `paste`, `undo`, `redo`, `revert`, `close_all`,
  `sel_invert`, `sel_hide`, `sel_unhide`, `invert_hide`.
- Other: `cmdseq`, `meshedit`, the `setview*` commands, `exit`.

Without Modeler reads, a result can only be checked by saving the
`.lwo` and reading the file. That's on hold with the rest of Modeler.

## Suggested order

1. Render output (category 1). It's the biggest gap: renders can't be
   directed to a file yet.
2. `AutoConfirm`/`AlertLevel` (category 12). It's quick, and a win
   would reduce dialog trouble everywhere.
3. `AddEnvelope` for the open node-input item (category 3).
4. Item management and selection (category 2).
5. Animation and motion (the rest of category 3).
6. Object, light and camera properties (categories 4-6), done the same
   way as `lw_set_camera`/`lw_set_light`.
7. Plug-ins and servers (category 9), which also answers the dynamics
   question.
