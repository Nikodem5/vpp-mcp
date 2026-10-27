# Writing UML sequence diagrams into Visual Paradigm `.vpp` files

This reference was written from memory after a task that added SD01–SD12 to
`zamawianie-jedzenia-uzupelniony.vpp`. That project uses VP build 20260914 and
DB_VERSION 20121026. The work was not confirmed by opening the result in VP. Every
format detail below was checked against VP-authored sample files, and
`verify.py` passes on the result. Where something is unverified, this file says so.

Working scripts are in
`vpp-sd/` (one-off scripts from the original lab work; not in this repo — their logic now lives in `vpp_mcp/`):

- `add_sd.py` is the generator.
- `verify.py` is the checker.
- `preview.py` renders a rough PNG from the stored geometry.
- `input.vpp` is a pristine copy of the input.
- `zamawianie-jedzenia-z-sekwencjami.vpp` is the output.

---

## 0. General `.vpp` facts (also relevant outside sequence diagrams)

- A `.vpp` file is a SQLite database. The tables are:
  - `PROJECT_INFO` (1 row). It has `DEFINITION` (blob) and two **text** columns:
    `ROOT_MODEL_ELEMENTS_DEFINITION` and `DIAGRAMS_DEFINITION`.
  - `MODEL_ELEMENT` with columns ID, USER_ID, USER_ID_PARENT, MODEL_TYPE, PARENT_ID, NAME,
    DEFINITION blob, MIRROR_SOURCE, AUTHOR, CREATE_AT (seconds), LAST_MOD_AT (seconds).
  - `DIAGRAM` with columns ID, DIAGRAM_TYPE, PARENT_MODEL_ID, NAME, DEFINITION.
  - `DIAGRAM_ELEMENT` with columns ID, SHAPE_TYPE, DIAGRAM_ID, MODEL_ELEMENT_ID,
    COMPOSITE_MODEL_ELEMENT_ADDRESS, REF_MODEL_ELEMENT_ADDRESS, PARENT_ID, DEFINITION.
  - `PROJECT_FILE` holds paths and gzip blobs: caches, documentation HTML and previews.
  - `TW_HISTORY` and `USER_ID_FORMAT`.
- A DEFINITION is UTF-8 text in VP's own object notation:
  - The header is `ID:"name":Type {` or `ID:NULL:Type {`.
  - Each top-level key is written as `\tkey=value;\n`.
  - Strings are `"..."` with `\"` and `\\` escapes. Non-ASCII characters (Polish letters) are stored raw.
  - References are `<id>` or `<path:to:id>`. `:` separates containment levels, and `$` addresses a member inside a row:
    - `Class$Operation`
    - `Frame:Lifeline$Activation`
    - `relRoot:container:assoc$endId`
  - A list is `key=(\n\t\t<a>, \n\t\t<b>\n\t);`. Items are separated by `", \n"` and the last item has no comma.
  - A nested object is `{ID:"name":Type {\n...\n}}`.
  - Colours are `(\n\t\tR, \n\t\tG, \n\t\tB, \n\t\tA\n\t)`.
  - Structured values are `(\n\t\t@k=v;, \n\t\t@k2=v2;\n\t)`. Every item except the last ends with `;, `, and the last ends with `;`.
- **Line endings.** This project, saved on Linux or macOS, uses LF. The Windows-saved GitHub samples use CRLF. Always write the project's own convention (LF here). The existing `PROJECT_INFO.DEFINITION` blob already contains some CRs; leave it alone.
- **IDs** are 16 characters from `[A-Za-z0-9._]`. Native IDs look like `xxxxIoWFYFAUBAkD`.
  - The earlier class-edit agent used 4 random characters + `IoWFYFAUC` + a 3-character counter.
  - I used 4 random characters + `IoWFYFAUD` + a 3-character counter.
  - Seed `random` so the output is deterministic.
  - Collect every existing row ID and nested `{ID:` first, so nothing collides.
- **Timestamps.** `pmCreateDateTime="ms"` and `pmLastModified="ms"` are quoted strings. `lastModifiedTime=ms;` is unquoted. Use values after the file's newest timestamp. The input's last VP save was 1792751623594; I used NOW = 1792760000000 plus a small counter.
- **Back-reference pattern.** A model element has `_masterViewId="<DE id>"` and `_modelViews=( {vid:"View":ModelView { container=<diagramId>; view="<DE id>"; }} )`. The DIAGRAM_ELEMENT has `metaModelElement=<full model path>`. The DIAGRAM has `Child=( <diagramId:DEid>, ... )`.
- Classes in this project are root elements (PARENT_ID NULL), so they are referenced as `<classId>`. An operation is `<classId$opId>`. If a class sits in a package, the path is `<pkg:class$op>`, as in the samples. Root-level `$` references already exist in VP files: `style=<StyleSet$style>` and DB `refColumn=<table$col>`.
- The sample class diagrams' DEs used an optional `style=<StyleSetContainer$styleId>`. I omitted `style` on all new shapes; several sample shapes also lack it. If you do add `style`, the StyleSetContainer also gets `StyleView` entries.

---

## 1. Overall structure of one sequence diagram

```
DIAGRAM row (DIAGRAM_TYPE='InteractionDiagram', PARENT_MODEL_ID NULL)
  _rootFrame=<FrameId>; Child=(<D:DE>...); customizedSortDiagramElementIds=("DE",...)
MODEL_ELEMENT Frame        (PARENT_ID NULL, NAME = diagram name, listed in rootModelElements)
  Child=( <F:actor>, <F:lifeline>..., <F:topLevelCombinedFragment>..., <F:gate> )
  gates=( <F:gate> )                              (only if gates exist)
  ├─ InteractionActor      (PARENT_ID = Frame)
  ├─ InteractionLifeLine   (PARENT_ID = Frame) with nested activations=( {Activation} )
  ├─ CombinedFragment      (PARENT_ID = Frame or an InteractionOperand)
  │    └─ InteractionOperand (PARENT_ID = CombinedFragment), guard={InteractionConstraint}
  │         ├─ nested CombinedFragment (PARENT_ID = operand)
  │         └─ InteractionOccurrence (ref) (PARENT_ID = operand or Frame)
  └─ Gate                  (PARENT_ID = Frame)
MODEL_ELEMENT ModelRelationshipContainer "Message" (PARENT_ID = "relationships" root container)
  └─ Message rows          (PARENT_ID = Message container)
```

- The Frame is **not drawn**: there is no Frame DE. Its `_modelViews=NULL` and it has no `_masterViewId`.
- The Frame's NAME equals the diagram name in the samples.
- Diagrams and frames go at the root: append the diagram ID to `DIAGRAMS_DEFINITION` and the frame ID to `ROOT_MODEL_ELEMENTS_DEFINITION`.

### Everything that must be appended or updated (new project with no SDs yet)

1. The `relationships` ModelRelationshipContainer (here `H9ZMBIWFYFAUBBNZ`):
   - Append `<relRoot:msgContainer>` to its `Child`.
   - Bump its top-level `pmLastModified` and LAST_MOD_AT.
2. Insert a new ModelRelationshipContainer row named `"Message"`:
   - PARENT_ID is the relationships container.
   - `Child` lists `<relRoot:msgContainer:msgId>` for every message.
   - Note: one Thesis sample lists the container under the root as `<gTlK...>` without a prefix. Others use `<root:child>`. VP accepted `<root:child>` when it re-saved the earlier agent's containers.
3. In PROJECT_INFO:
   - Append to ROOT_MODEL_ELEMENTS_DEFINITION `Child`: each Frame ID, as `<FrameId>`.
   - Append to DIAGRAMS_DEFINITION `Child`: each diagram ID.
4. No back-references are needed on Classes or Operations. Lifelines that point to a class, and messages that point to an operation, add nothing to the class or operation definitions. I verified this in Thesis.vpp.
5. I added no `PROJECT_FILE` entries (see §9).

---

## 2. DIAGRAM row (InteractionDiagram)

The key set below was copied from Thesis.vpp. Write it with LF. `initializeDiagramForCreate=T` is present in almost all samples; the existing class diagram has it too.

```
<D>:"SD06 Śledź status zamówienia":InteractionDiagram {
	paintConnectorThroughLabel=1;
	_shapeGroups=NULL;
	diagramBackground=(255,255,255,255 as colour block);
	connectorLabelOrientation=0;
	showMessageStereotype=T;
	showPackageNameStyle=0;
	showDefaultPackage=F;
	pointConnectorEndToCompartmentMember=T;
	autoFitShapesSize=F;
	connectorStyle=1;
	diagramPreviewData_name=NULL;
	showSequenceNumbers=T;
	_interactionDiagramLayoutOptions=(
		@absoluteLifelineSpacingDistance=80;, 
		@absoluteMessageSpacingDistance=30;, 
		@handleLabelsWhenLayout=T;, 
		@lifelineSpacing=0;, 
		@messageSpacing=0;, 
		@realTimeLayout=F;
	);
	_globalPaletteOption=T;
	connectionPointStyle=0;
	gridWidth=10;
	pmCreateDateTime="<ms>";
	showActivations=T;
	alignToGrid=F;
	customizedSortDiagramElementIds=(
		"<DE id>", 
		...every DE of this diagram...
	);
	diagramPreviewData_id="<fresh id>";      (SGT.vpp has ids with no preview file; fine)
	autoExtendActivations=T;
	pmLastModified="<ms>";
	hiddenDiagramElementIds=NULL;
	gridVisible=F;
	creationTime=<ms>;
	showMessagesOperationSignature=T;
	pmAuthor="user";
	lastModified=<ms>;
	connectorLineJumpsSize=0;
	showStereotypes=T;
	shapePresentationOption=0;
	connectorModelElementNameAlignment=4;
	voiceIds=NULL;
	displayLifeLinesAsRobustnessAnalysisIcon=0;
	initializeDiagramForCreate=T;
	referenceMappingReferencedElementIds=NULL;
	_rootFrame=<FrameId>;
	Child=(
		<D:DEid>, 
		...
	);
	referenceMappingElementIds=NULL;
	modelElementNameAlignment=4;
	showActivityStateNodeCaption=524287;
	connectorLineJumps=0;
	gridHeight=10;
	gridColor=(192,192,192,255);
	showModelElementIdModelTypes=NULL;
}
```

- `customizedSortDiagramElementIds` must contain exactly the diagram's DE IDs. The samples list them in creation order; it may be z-order. I wrote fragments and operands first, so they sit behind everything, then occurrences, lifelines with their activations, gates, and messages last.
- `Child` (`<D:DE>`) must equal the set of DIAGRAM_ELEMENT rows for the diagram, **including** nested child shapes and activations.
- Frame model element (Thesis):

```
.eqaJcaGAqACJQdi:"PayByCreditCard":Frame {
	pmLastModified="1588758345660";
	pmAuthor="Peerawut";
	Child=(
		<.eqaJcaGAqACJQdi:Lc6aJcaGAqACJQdv>, 
		<.eqaJcaGAqACJQdi:9lmaJcaGAqACJQd_>, 
		<.eqaJcaGAqACJQdi:nocWJcaGAqACJQrH>, 
		<.eqaJcaGAqACJQdi:YjYGl46GAqACJhKy>
	);
	pmCreateDateTime="1527470708639";
	_modelViews=NULL;
	lastModifiedTime=1588758342758;
	_modelEditable=T;
}
```

The OpenSection frame from Thesis shows the form with a gate:
`gates=( <F:gateId> );` plus `Child` also contains `<F:gateId>`.

---

## 3. Lifelines and actors

### InteractionLifeLine (model element, PARENT_ID = Frame)

```
9lmaJcaGAqACJQd_:"s1":InteractionLifeLine {
	_modelEditable=T;
	_masterViewId="9lmaJcaGAqACJQd.";
	baseClassifier=<zFSUMcaGAqACJRdO:wzZ1ocaGAqACJQ8L>;      (root class → <classId>)
	pmAuthor="Peerawut";
	FromEndRelationships=(
		<VgDTocaGAqACJRA9:gTlK.caGAqACJQld:5qhaJcaGAqACJQeT$5qhaJcaGAqACJQeU>
	);
	lastModifiedTime=1588758289267;
	pmCreateDateTime="1527470725743";
	_modelViews=( {GVmaJcaGAqACJQeA:"View":ModelView { container=<seqaJcaGAqACJQdX>; view="9lmaJcaGAqACJQd."; }} );
	ToEndRelationships=(
		<VgDTocaGAqACJRA9:gTlK.caGAqACJQld:cBJaJcaGAqACJQeh$cBJaJcaGAqACJQej>
	);
	activations=(
		{06haJcaGAqACJQea:"Activation":Activation {
			_masterViewId="86haJcaGAqACJQec";
			pmAuthor="Peerawut";
			pmCreateDateTime="1527470757323";
			_modelViews=(
				{86haJcaGAqACJQed:"View":ModelView {
					container=<seqaJcaGAqACJQdX>;
					view="86haJcaGAqACJQec";
				}}
			);
			_modelEditable=T;
		}}
	);
	pmLastModified="1588758337020";
}
```

- `baseClassifier=<classId>` binds the lifeline to a class. VP then displays `name : Class`. Some samples use `baseClassifier_string="X"` (an unbound type name).
- **":Klient"** is an anonymous lifeline: header `id:"":InteractionLifeLine`, NAME column `''`. Thesis has one.
- `From/ToEndRelationships` list `<msgPath$messageEndId>` for every message end that touches this lifeline. They must match the messages exactly.
- `stopped=T` appears on a lifeline that has a destroy message (not used).

### InteractionActor (actor lifeline)

```
Lc6aJcaGAqACJQdv:"Actor":InteractionActor {
	FromEndRelationships=(
		<VgDTocaGAqACJRA9:gTlK.caGAqACJQld:cBJaJcaGAqACJQeh$cBJaJcaGAqACJQei>
	);
	_masterViewId="Lc6aJcaGAqACJQdu";
	pmLastModified="1527470786287";
	pmAuthor="Peerawut";
	pmCreateDateTime="1527470715828";
	_modelViews=( ...ModelView container=<diagram> view="Lc6aJcaGAqACJQdu"... );
	_modelEditable=T;
}
```

It may also have `ToEndRelationships` and `lastModifiedTime`. An actor has **no activations**: messages to and from it have no from/toActivation.

**Use-case Actors were not bound.** In every sample (SGT.vpp has 6 `Actor`s and 29 `InteractionActor`s with the same names) the InteractionActor is a separate model element with no reference to the use-case Actor. Neither element references the other. I followed that: one InteractionActor per diagram, named like the use-case Actor ("Klient", "System płatności", …). The checker confirms a use-case Actor with the same name exists. Binding the two (for example `baseClassifier=<ActorId>`) is unverified; don't do it without a sample.

---

## 4. Messages

All messages live in the ModelRelationshipContainer `"Message"` under `relationships`. Their path is `<relRoot:msgContainer:msgId>`. The name may be NULL: a call bound to an operation usually has `NULL` or `""` as its name.

### Type codes and action types

| kind | `type=` | `actionType` | activations |
|---|---|---|---|
| synchronous call | (absent) | `{id:"Call":ActionTypeCall { operation=<Class$Op>; ... }}` | `fromActivation` (if the sender is a lifeline) + `toActivation` (new activation on the receiver) |
| create | `type=2;` name `"create"` (SGT uses `"<<create>>"`) | ActionTypeCall **without** `operation`, or no actionType at all | `fromActivation` only; never `toActivation` (43 of 43 sample creates) |
| self | `type=3;` | ActionTypeCall with operation | `fromActivation` == `toActivation` (the same activation) |
| recursive | `type=4;` | Call | toActivation is a nested activation `Frame:LL$act$subAct` (seen once; not used) |
| `type=1` | seen once in SGT (meaning unclear, perhaps duration); not used | | |
| return / reply | (absent) | `{id:"Return":ActionTypeReturn {...}}` | `fromActivation` = the callee's activation, `toActivation` = the caller's activation (absent if the target is an actor) |
| send / asynchronous signal | (absent) | `{id:"Send":ActionTypeSend {...}}` | seen in Senior Project.vpp (not used) |
| plain named message (my 'sig' to an external actor) | (absent) | none | fromActivation only |
| destroy | | `ActionTypeDestroy` | (Thesis) |
| "found" message | modelled as a message whose **from end is a Gate** (see §6) | Call | toActivation only |

- Optional keys:
  - `transitFrom="(Class$Op)"` is model-transitor bookkeeping and not needed.
  - `recurrenceCondition` lives inside actionType.
- **Return linkage:** the call message has `returnMessage=<relRoot:msgContainer:returnMsgId>;`.
- **Arguments:** no sample stored actual arguments (`zmienStatus(OPLACONE)`). There is no `arguments` key in any sample. VP displays the bound operation's signature instead (`showMessagesOperationSignature=T`).

### Call message definition (generated, mirrors Thesis)

```
f6VsIoWFYFAUDAI9:NULL:Message {
	toActivation=<FRAME:LIFELINE_TO$ACT>;
	_modelEditable=T;
	actionType={YLZCIoWFYFAUDAJZ:"Call":ActionTypeCall {
		operation=<O.1YIoWFYFAUBAmH$F5z_IoWFYFAUCAAQ>;
		pmAuthor="user";
		pmCreateDateTime="1792760000327";
		_modelViews=NULL;
		lastModifiedTime=1792760000327;
		_modelEditable=T;
	}};
	fromActivation=<FRAME:LIFELINE_FROM$ACT>;
	_masterViewId="<DE id>";
	pmAuthor="user";
	lastModifiedTime=1792760000327;
	pmCreateDateTime="1792760000327";
	_modelViews=(
		{d9TBIoWFYFAUDAJa:"View":ModelView {
			container=<DIAGRAM>;
			view="<DE id>";
		}}
	);
	sequenceNumber="1.3";
	returnMessage=<H9ZMBIWFYFAUBBNZ:2wcZIoWFYFAUDAAB:KeKaIoWFYFAUDAJB>;
	from={4DkCIoWFYFAUDAI_:NULL:MessageEnd {
		pmAuthor="user";
		pmCreateDateTime="1792760000327";
		_modelViews=NULL;
		Direction=0;
		_modelEditable=T;
		EndModelElement=<FRAME:LIFELINE_FROM>;
	}};
	to={cq8JIoWFYFAUDAJA:NULL:MessageEnd {
		...
		Direction=1;
		_modelEditable=T;
		EndModelElement=<FRAME:LIFELINE_TO>;
	}};
	pmLastModified="1792760000327";
}
```

Create message (Thesis):

```
5qhaJcaGAqACJQeT:"create":Message {
	_modelEditable=T;
	fromActivation=<.eqaJcaGAqACJQdi:9lmaJcaGAqACJQd_$06haJcaGAqACJQea>;
	_masterViewId="OahaJcaGAqACJQeW";
	...
	sequenceNumber="1.1";
	type=2;
	from={...EndModelElement=<.eqaJcaGAqACJQdi:9lmaJcaGAqACJQd_>;}};
	to={...EndModelElement=<.eqaJcaGAqACJQdi:EAuaJcaGAqACJQeK>;}};
	pmLastModified="1561810141026";
}
```

Banking.vpp has the same structure plus an `actionType={..:"Call":ActionTypeCall {...no operation...}};`.

Return message (Thesis):

```
5tx6JcaGAqACJQlz:"paymentSuccess":Message {
	toActivation=<.eqaJcaGAqACJQdi:9lmaJcaGAqACJQd_$06haJcaGAqACJQea>;
	_modelEditable=T;
	actionType={Kdx6JcaGAqACJQl4:"Return":ActionTypeReturn {
		pmAuthor="Peerawut";
		pmCreateDateTime="1527471029140";
		_modelViews=NULL;
		_modelEditable=T;
	}};
	fromActivation=<.eqaJcaGAqACJQdi:EAuaJcaGAqACJQeK$ZWnaJcaGAqACJQff>;
	... sequenceNumber="1.3"; from/to MessageEnds ...
}
```

### Activations

- Activations are **nested objects inside the lifeline** (`activations=( {actId:"Activation":Activation {...}} )`). They are not rows.
- Their address is `<Frame:Lifeline$actId>`. That address is used in `fromActivation`/`toActivation` and in the activation DE.
- Activation DE row:
  - `SHAPE_TYPE='Activation'`
  - **`MODEL_ELEMENT_ID` NULL**
  - `COMPOSITE_MODEL_ELEMENT_ADDRESS='Frame:Lifeline$actId'`
  - `metaModelElement=<same address>`
- The ModelView for an activation sits inside the nested Activation block, indented 3–5 tabs.
- The earlier agent's `verify_vpp.py` reports activations as errors ("model None missing" and "ModelView … has no matching DE"). Those reports are expected. `verify.py` handles activations correctly.

### Sequence numbering (VP's scheme; my implementation)

- Each activation has a context number. A message sent from an activation with context `C` gets `C.k`, where k counts per activation.
- A message from an actor, or a found message, gets the next root number `n`.
- A call creates a new activation on the receiver whose context is the call's number.
- A return is numbered in the context of the **receiver's** (caller's) activation. A return to an actor takes the next root number. In Thesis, the reply to 1.2 was numbered 1.3, and the reply to 1.2.1 was 1.2.2.
- A self message is numbered in the sender's context and creates no new context.
- In VP itself, a lifeline that sends after being created gets a new activation not started by any incoming message, numbered at the top level (`"2"` in Thesis). I instead gave such an activation the create message's number as its context (3.3 → 3.3.1, 3.3.2…). This is clearer, and the stored strings are just what VP displays.
- The activation stack (in `add_sd.py`, class `SD`):
  - A call pops the stack down to the sender.
  - A return pops the callee and everything above it.
  - A message from an actor clears the stack.
  - At the start of each `alt` operand the stack is **restored** to the snapshot taken at fragment start, so alternative branches reuse the same caller activation. Afterwards the stack is whatever the last operand left.

---

## 5. CombinedFragment / InteractionOperand / InteractionUse

### Operator codes (`interactionOperator=`)

These follow the alphabetical UML operator list starting at 65:
65 alt, 66 assert, 67 break, 68 consider, 69 critical, 70 ignore, 71 loop, 72 neg, 73 opt, 74 par, 75 seq, 76 strict.

Confirmed by guards in the samples: **65 alt**, **67 break** (SGT error exits), **71 loop** ("For each Enrollment", "a : alunos"), **73 opt**. The others are inferred.

### Model

```
nocWJcaGAqACJQrH:"success == true":CombinedFragment {      (name is free; VP default "CombinedFragment", "CombinedFragment2"...)
	_modelEditable=T;
	interactionOperator=65;
	_masterViewId="nocWJcaGAqACJQrG";
	pmAuthor="Peerawut";
	pmCreateDateTime="1527471726969";
	_modelViews=( ...view="nocWJcaGAqACJQrG"... );
	coveredLifeLines=(
		<.eqaJcaGAqACJQdi:9lmaJcaGAqACJQd_>, 
		<.eqaJcaGAqACJQdi:EAuaJcaGAqACJQeK>
	);                                             (may include InteractionActors — SGT does)
	Child=(
		<.eqaJcaGAqACJQdi:nocWJcaGAqACJQrH:uYcWJcaGAqACJQrL>, 
		<.eqaJcaGAqACJQdi:nocWJcaGAqACJQrH:fYcWJcaGAqACJQrR>
	);
	pmLastModified="1527471763089";
}
uYcWJcaGAqACJQrL:"Save to Repo":InteractionOperand {      (default names "Operand", "Operand2"...)
	_modelEditable=T;
	_masterViewId="uYcWJcaGAqACJQrK";
	messages=(
		<VgDTocaGAqACJRA9:gTlK.caGAqACJQld:o.o6JcaGAqACJQgM>
	);
	pmAuthor="Peerawut";
	lastModifiedTime=1588758289500;
	pmCreateDateTime="1527471727005";
	guard={5EiWJcaGAqACJQrb:"InteractionConstraint":InteractionConstraint {
		pmAuthor="Peerawut";
		pmCreateDateTime="1527471739431";
		_modelViews=NULL;
		lastModifiedTime=1558849819322;
		constraint="paymentSuccess = true";       (no brackets; VP adds [ ]; "else" for else)
		_modelEditable=T;
	}};
	_modelViews=( ...view="uYcWJcaGAqACJQrK"... );
	Child=( <path:to:nestedCF> );             (only if nested fragments / refs)
	pmLastModified="1588758337024";
}
```

- **Message membership.** `messages=( … )` lists only the messages **directly** in that operand. A message inside a nested fragment belongs only to the innermost operand; I checked this across all SGT operands.
- **Nesting.**
  - A nested CF row has PARENT_ID = the operand.
  - The full path grows with each level, e.g. `<Frame:CF:Operand:CF2>` and `<Frame:CF:Op:CF2:Op2>`. Both the `Child` lists and `metaModelElement` use the full path.
  - The Frame's `Child` lists only top-level CFs.
- **InteractionOccurrence (ref)** can be a child of the Frame or of an operand (SGT has 5 inside operands):

```
AeijJQaGAqBwARVY:"InteractionUse":InteractionOccurrence {
	refersTo=<zekzJQaGAqBwAQqh>;              (= the **Frame id** of the referenced diagram)
	coveredLifeLines=(
		<5UvgxQaGAqBwAQWN:cpQQxQaGAqBwAQWZ>
	);
	_masterViewId="AeijJQaGAqBwARVX";
	pmLastModified="1514601914289";
	pmAuthor="matia";
	pmCreateDateTime="1514592868224";
	_modelViews=( ...view="AeijJQaGAqBwARVX"... );
	_modelEditable=T;
}
```

I named it after the target diagram ("SD04 Opłać zamówienie"). Thesis names it the same way, and SGT uses "InteractionUse". Pre-allocate the frame IDs of all diagrams so forward refs work: SD03 refers to SD04.

---

## 6. Gate (used for the SD11 "found message")

None of the samples had a filled-circle found message, and no message type code for one was seen. The only "message from nowhere" in the samples is a message whose `from` end is a **Gate**, which VP draws as a small square on the frame or diagram boundary (Banking ProcessDeposit, Thesis OpenSection).

```
Engh9A6GAqACKBKQ:"Gate":Gate {               (PARENT_ID = Frame; Frame gates=( <F:gate> ) + in Child)
	_modelEditable=T;
	_masterViewId="...";
	pmAuthor="Peerawut";
	FromEndRelationships=(
		<ur750A6GAqACKA4B:lmjbqA6GAqACKA1P:VP0h9A6GAqACKBKt$VP0h9A6GAqACKBKu>
	);
	lastModifiedTime=...;
	pmCreateDateTime="...";
	_modelViews=( ... );
	pmLastModified="...";
}
```

The message has `from={...EndModelElement=<Frame:GateId>;}`, no fromActivation, and a toActivation on the receiver. Its number is a root number.

The Gate DE (Banking):

```
7ngh9A6GAqACKBKU:"Gate":Gate {
	_fillColor=(@gradientStyle=1;, @transparency=100;, @type=1;, @color1=(122,207,245,0););
	background=(122,207,245,255);
	connectionPointType=1;
	width=20;
	_captionUIModel=(@x=-12;, @y=20;, @width=44;, @height=15;, @side=1;, @visible=T;, @internalWidth=-2147483648;, @internalHeight=-2147483648;);
	_elementFont=(...size 11...);
	metaModelElement=<Mtq.9A6GAqACKBEH:Engh9A6GAqACKBKQ>;
	foreground=(192,192,192,255);
	y=120;
	overrideAppearanceWithStereotypeIcon=T;
	x=98;
	_lineModel=(...colour 192,192,192...);
	height=20;
}
```

The message connector from a gate has `_points="10,10;<x>,<y>;"`: the first point is the gate centre, relative to the gate shape.

---

## 7. DIAGRAM_ELEMENT shapes and connectors

| SHAPE_TYPE | MODEL_ELEMENT_ID | other columns |
|---|---|---|
| InteractionLifeLine | lifeline ME | |
| InteractionActor | actor ME | |
| Activation | NULL | COMPOSITE_MODEL_ELEMENT_ADDRESS = `Frame:LL$act` |
| Message (connector) | message ME | |
| CombinedFragment | CF ME | PARENT_ID = operand DE if nested |
| InteractionOperand | operand ME | always top level (no PARENT_ID), **absolute** coordinates |
| InteractionOccurrence | occurrence ME | PARENT_ID = operand DE if inside an operand |
| Gate | gate ME | |

**Nested shapes (verified in SGT, and the same convention appears in the 2026 input for UseCase inside System):**
- A child DE has `PARENT_ID` = the parent DE ID.
- It has a key `_parent=<Diagram:parentDE>;`.
- Its `x`/`y` are **relative to the parent shape**.
- It is still listed in the diagram's `Child`.
- Inner operands of a nested CF are **not** children: they keep absolute coordinates. Only the CF itself and occurrences are children of the operand.

### Lifeline / actor DE (Thesis; I changed the font to 11)

```
9lmaJcaGAqACJQd.:"s1":InteractionLifeLine {
	foreground=(0,0,0,255);
	customText="";
	parentFrame=<.eqaJcaGAqACJQdi>;
	connectToPoint=T;
	y=40;
	x=441;
	metaModelElement=<.eqaJcaGAqACJQdi:9lmaJcaGAqACJQd_>;
	overrideAppearanceWithStereotypeIcon=T;
	parentConnectorHeaderLength=40;
	parentConnectorLineLength=10;
	height=486;                       (header + dashed line, to diagram bottom)
	_fillColor=(@gradientStyle=1;, @transparency=0;, @type=1;, @color1=(255,255,255,255););
	width=96;
	background=(255,255,255,255);
	style=<...>;                      (optional; I omitted it)
	_elementFont=(@name="Dialog";, @color=(0,0,0,255);, @size=14;, @style=0;);
	_captionUIModel=(@x=0;, @y=8;, @width=96;, @height=19;, @side=1;, @visible=T;, @internalWidth=-2147483648;, @internalHeight=-2147483648;);
	_lineModel=(@cap=0;, @transparency=0;, @weight=1.0;, @color=(0,0,0,255);, @hasStroke=T;);
}
```

The InteractionActor DE has the same keys. Width is 60; the caption is `@x=4;@y=35;@width=53;@height=19` (below the stick figure).

### Activation DE

```
86haJcaGAqACJQec:"Activation":Activation {
	parentConnectorHeaderLength=40;
	_fillColor=(...white...);
	background=(122,207,245,255);
	width=8;
	_captionUIModel=(@x=485;, @y=145;, @width=8;, @height=361;, @side=7;, @visible=F;, ...);   (= own bounds, invisible)
	_elementFont=(...);
	metaModelElement=<.eqaJcaGAqACJQdi:9lmaJcaGAqACJQd_$06haJcaGAqACJQea>;
	foreground=(0,0,0,255);
	connectToPoint=T;
	y=145;
	overrideAppearanceWithStereotypeIcon=T;
	x=485;                            (= lifeline.x + lifeline.width/2 - 4; absolute)
	_lineModel=(...);
	height=361;
	parentConnectorLineLength=10;
}
```

### Message connector DE

```
XBJaJcaGAqACJQek:"":Message {          (header name = message name, NULL ok)
	background=(0,0,0,255);
	width=336;
	toPinType=1;
	useToShapeCenter=T;
	_captionUIModel=(@x=6;, @y=-60;, @width=226;, @height=54;, @side=1;, @visible=T;, @internalWidth=226;, @internalHeight=53;);
	_toShape=<seqaJcaGAqACJQdX:9lmaJcaGAqACJQd.>;       (the LIFELINE DE, not the activation)
	_elementFont=(...);
	_points="34,130;44,130;";
	metaModelElement=<VgDTocaGAqACJRA9:gTlK.caGAqACJQld:cBJaJcaGAqACJQeh>;
	fromPinType=1;
	foreground=(0,0,0,255);
	y=80;
	_fromShape=<seqaJcaGAqACJQdX:Lc6aJcaGAqACJQdu>;
	x=-16;
	_lineModel=(...);
	height=100;
	useFromShapeCenter=T;
}
```

**Geometry conventions (derived and confirmed numerically on Thesis and OpenSection):**

- `_points`: the first point is relative to the `_fromShape` (lifeline/actor/gate DE x,y). The **last point is relative to the `_toShape`**. A self message's intermediate points are relative to the from shape.
- Endpoints are drawn at activation edges:
  - from: right edge (`act.x+8`) if the target is to the right, else the left edge.
  - to: left edge (`act.x`) if the source is to the left, else `act.x+8`.
  - An actor end, or an end without an activation, uses the shape centre.
- A message's y equals its activation's top + 8.
- Create message: the last point is `0,17` relative to the created lifeline. The created lifeline's `y` = message y − 17, so its head sits on the arrow.
- Self message: `"x,y; x+30,y; x+30,y+20; x,y+20;"` from the activation's right edge.
- Bounding box (`x`,`y`,`width`,`height`), with all points expressed in from-shape-relative coordinates: `x=min(px)-50`, `y=min(py)-50`, `width=maxx-minx+100`, `height=maxy-miny+100`. A self message gives width 130, height 120. This matches the samples exactly.
- Caption `@x/@y` are relative to the **first point**:
  - Normal message: `@x=(dx-capW)/2` (centred; negative for right-to-left arrows), `@y≈-capH-6`.
  - Self message: `@x=36;@y=2`.
  - Caption height is 15 for font 11 and 19 for font 14.
  - `internalWidth/Height=-2147483648` means auto size.

### CombinedFragment DE

```
nocWJcaGAqACJQrG:"success == true":CombinedFragment {
	parentConnectorHeaderLength=40;
	_fillColor=(@gradientStyle=1;, @transparency=100;, @type=1;, @color1=(122,207,245,0););
	background=(122,207,245,255);
	width=654;
	_captionUIModel=(@x=0;, @y=0;, @width=23;, @height=18;, @side=12;, @visible=T;, ...);   (operator tab: alt 23, loop ~30-40, break 46)
	_elementFont=(...size 11...);
	metaModelElement=<.eqaJcaGAqACJQdi:nocWJcaGAqACJQrH>;
	foreground=(0,0,0,255);
	connectToPoint=T;
	y=364;
	overrideAppearanceWithStereotypeIcon=T;
	x=450;
	[_parent=<D:operandDE>;]           (only when nested; x/y then relative)
	_lineModel=(...);
	height=165;
	parentConnectorLineLength=10;
}
```

### InteractionOperand DE

It has the same key set as the CF DE. In the sample, `_fillColor` has `@transparency=0;` with colour (122,207,245,255); VP does not visibly fill operands. The caption is invisible, `side=7`.

The first operand's `y` = CF `y + 18` (below the operator tab). Each later operand starts where the previous one ends, and the last operand ends at the CF bottom. All operands share the CF's x and width.

### InteractionOccurrence DE (SGT)

```
AeijJQaGAqBwARVX:"InteractionUse":InteractionOccurrence {
	foreground=(0,0,0,255);
	creatorDiagramType="InteractionDiagram";
	_durationConstraintUIInfo=NULL;
	connectToPoint=T;
	y=102;  x=13;                         (relative to parent operand)
	metaModelElement=<5UvgxQaGAqBwAQWN:...:I8L6xQaGAqBwAQr8:AeijJQaGAqBwARVY>;
	overrideAppearanceWithStereotypeIcon=T;
	parentConnectorHeaderLength=40;
	parentConnectorLineLength=10;
	height=50;
	_fillColor=(...transparency 100...);
	width=382;
	background=(122,207,245,255);
	_parent=<GUvgxQaGAqBwAQWJ:I8L6xQaGAqBwAQr7>;
	_elementFont=(...);
	_captionUIModel=(@x=0;, @y=0;, @width=382;, @height=50;, @side=12;, @visible=T;, ...);
	_lineModel=(...);
	gateShapeUIModelIds=( "..." );      (only when the ref has gates; omitted by me)
}
```

---

## 8. Layout heuristics used in add_sd.py

- Lifeline header at y=60; header height assumed 35; the first message at y=140.
- Width estimate `tw()`:
  - narrow characters (`il.,:;'!|()[]` and space): 3.5 px
  - m/w: 9 px
  - uppercase: 7.5 px
  - everything else: 6.2 px
  - This is for Dialog 11.
- Object lifeline width = max(100, tw("name : Class")+26). Actor width = max(60, tw(name)+14).
- Gaps between lifeline centres:
  - Start at max(190, (wᵢ+wᵢ₊₁)/2+50).
  - Each message label needs min(tw(label),430)+40 across its span; if the gaps are short, spread the deficit evenly over the gaps it spans.
  - A self message needs label + 80 to the right.
  - The label used is `seq: op(p : T, …) : Ret`, built from the model signature, because VP shows the signature.
- Vertical spacing:
  - Normal message: 40.
  - Self message: 55.
  - Create message: placed at cursor+5, with the next message at y+45.
  - Fragment start: top = cursor−10, then cursor += 55.
  - Each later operand: separator = cursor−15, then cursor += 45.
  - Fragment end: bottom = cursor−20, then cursor += 10.
  - Ref: top = cursor−10, height 40, then cursor += 50.
  - Diagram bottom = cursor+10. All lifelines end there.
- Fragment x-range covers the lifelines involved, recursively, plus ref coverage. Padding is 30 − 9·depth, so outer fragments contain inner ones.
- Activation runs from (first y − 8) to (last y + 10). A caller is extended to cover its synchronous callees' activations plus 5.
- Gate x = target centre − 120, gate y = message y − 10.

**What may render oddly:**
- Label widths are estimates. VP may draw long signatures (e.g. `ocenZamowienie(...)`) over neighbouring lifelines, or diagrams may come out wide.
- Guard text could crowd the first message.
- Created objects that send messages get an activation not started by any incoming message.
- Return numbering such as "2: status" is VP-consistent but may surprise readers.
- `autoExtendActivations=T` means VP may resize activations.

---

## 9. Uncertainties

- **Constructor binding on a create message** (SD03 `Zamowienie(...)`): ActionTypeCall with `operation=<Class$ctor>` on a `type=2` message. The structure is valid, but no sample did it; samples' create actionTypes have no operation. Fallback: drop `operation`.
- **No PROJECT_FILE caches for new diagrams** (`vpdiagramshapes/<D>.vps/details.xml`, `HTMLStringProperties/<D>_documentation`, `diagramPreviewData/<id>`). These are gzip caches written on save. One StubAndDriverGenerator diagram lacked shapes, many lacked documentation, and all SGT preview IDs had no file. I expect VP to regenerate them.
- **Gate vs found message:** the found message is a Gate-sourced message, not UML's filled circle.
- **Actor binding:** see §3. Not bound, following the samples.
- **Sample age:** the samples come from VP builds 2017–2020 (same DB_VERSION 20121026). On a class diagram, a class DE and an association DE, the input's 2026 build differed by only 2 new diagram keys. Interaction keys are assumed unchanged.
- **Message arguments** are not stored (no format known).
- The meanings of operator codes other than 65/67/71/73 and of message `type=1` are inferred.

## 10. Verification checklist (what verify.py does)

1. `PRAGMA integrity_check`, `foreign_key_check`.
2. Every DEFINITION parses: string-aware tokenizer, balanced `{}`/`()`, header ID equals the row ID and header type equals MODEL_TYPE/SHAPE_TYPE/DIAGRAM_TYPE. No CR in new rows.
3. IDs are unique across rows and nested `{ID:` objects. Every `<ref>` segment, split on `:` and `$`, resolves.
4. Each DE `metaModelElement` ends in MODEL_ELEMENT_ID. The model element has a ModelView (container = diagram, view = DE) and `_masterViewId`. Each activation DE address matches its nested Activation block and that block's view. `_fromShape`/`_toShape`/`_parent` are in the same diagram; `_parent` equals PARENT_ID.
5. Diagram `Child` equals its DE rows, `customizedSortDiagramElementIds` equals its DE rows, and `_rootFrame` is a Frame with the same name.
6. The `Child` of every ModelRelationshipContainer, Frame, CombinedFragment and InteractionOperand equals the rows with that PARENT_ID, with correct full paths. Frame `gates` ⊆ `Child`. rootModelElements = rows with PARENT_ID NULL, and rootDiagrams = DIAGRAM rows.
7. Messages:
   - Each MessageEnd is listed in the end's From/ToEndRelationships, and there are no dangling ones.
   - Activations belong to the end lifeline.
   - A message to a lifeline has a toActivation, except creates. A message from a lifeline has a fromActivation.
   - A self message has from = to and the same activation.
   - The operation exists and its owner is the receiver's baseClassifier or a supertype (Generalization/Realization: `fromModel` = general/interface, `toModel` = specific).
   - A create message's operation must be a constructor.
   - `returnMessage` is consistent.
   - The view endpoints are the end elements' views.
8. Content matches `sd_data.py`: participants and their order, messages sorted by y against the flattened items (kind, ends, operation name and argument count, labels), and fragment path (operator, operand index, guard) per message and ref.
9. Geometry: each message lies inside its operand's y-range, each activation inside its lifeline, and participants run left to right.
10. Diff against the input: no row removed or changed, except the relationships container (`Child` appended + pmLastModified) and the PROJECT_INFO root lists (append-only).
11. Negative test: a wrong operation owner and a message dropped from an operand were both detected.

The earlier agent's `vpp-edit/verify_vpp.py` reports 2 errors per activation (136 here). These are expected; it doesn't know about composite activation DEs.

## 11. Template sources

Clone with `git clone --depth 1 --filter=blob:none --no-checkout` and then `git checkout HEAD -- '*.vpp'`. GitHub search API and gh API calls to unattached repos are blocked in this environment; plain git clone works. Read the files only with `python3 -I` + sqlite3 (`mode=ro`), then delete them.

- https://github.com/peerawutgaga/VPP-Project (VP 20191113 / build 20200108 unless noted)
  - `Thesis.vpp`:
    - PayByCreditCard: actor, lifelines, create, call, return, destroy, alt with 2 operands
    - GetGPAX: loop (71) and recursive type=4
    - OpenSection: self message, create, Gate message, InteractionOccurrence
    - Frames with `gates`
  - `Banking.vpp`: Gate-sourced messages, create messages with an empty ActionTypeCall, InteractionOccurrence + gates.
  - `TestCase.vpp`, `StubAndDriverGenerator.vpp`: many self/create messages, alt.
  - `Archived/Senior Project.vpp` (2018): root-level class baseClassifier `<id>`, ActionTypeSend.
- https://github.com/mendess/SGT, `Report/VPP/SGT.vpp` (VP 2017):
  - 29 sequence diagrams with alt/break/loop/opt
  - nested fragments as operand children (`_parent`, relative coordinates)
  - InteractionOccurrence inside operands with coveredLifeLines
  - actors in coveredLifeLines
  - InteractionActor next to unbound use-case Actors
- Not useful: BlueGhost147/BPMN2UML, safir-medjeber/cpp_project (no sequence diagrams); LING71671/vpce had no .vpp.

## 12. Scripts and reusable parts

`vpp-sd/` (one-off scripts from the original lab work; not in this repo — their logic now lives in `vpp_mcp/`)

- **`add_sd.py`** (`python3 -I add_sd.py`; rebuilds from `input.vpp`, deterministic, writes `add_sd_log.txt`). It reads `../build/sd_data.py`.
  - `new_id()`, `ts()`, `q()`, `hdr()`, `reflist()`, `views()`, `color()`, `fill()`, `caption()`, `FONT`, `LINE`, `GLINE` are generic serialization helpers.
  - `Model`:
    - parses classes, operations with parameter names and types, actors, and supertypes
    - `resolve(classId, "op(a, b)")` matches by name and argument count, walking supertypes; it aborts on missing or ambiguous matches
  - `Act` is the activation object; `path(frame)` gives its address.
  - `SD`:
    - `run()`/`items()`: semantic pass with numbering, activation stack and vertical cursor
    - `layout()`: horizontal positions, activation extents, fragment and ref boxes
    - `build(db)`: inserts all MODEL_ELEMENT, DIAGRAM and DIAGRAM_ELEMENT rows
    - `label()`
  - `append_ref_list(s, key, refs)` and `touch_top(s)` handle list appends.
  - `main()` adds the Message container, updates relationships, and appends to PROJECT_INFO.
  - The input format (sd_data items) is: `call/self/create/ret/found/sig`, `loop/opt (guard, items)`, `alt [(guard, items)…]`, `ref (diagramName, [participants])`. Participants are `('actor', name)` or `('obj', name, Class, created)`.
- **`verify.py`** (`python3 -I verify.py [out.vpp] [input.vpp]`) implements §10. Reusable parts: `tokenize()`, `lst()`, `gi()`, and the generic sections A–F and H; section G is specific to sd_data.
- **`preview.py`** (`python3 -I preview.py file.vpp outdir`) draws a PNG per InteractionDiagram from the stored DE geometry with PIL, resolving `_parent` relative coordinates. Use it to eyeball the layout; it does not reproduce VP rendering.
