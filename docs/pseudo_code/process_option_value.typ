#import "@preview/lovelace:0.3.1": *

#pseudocode-list[
  #text(font: "New Computer Modern", features: ("smcp",), [Process-Option-Value]) ($o, (O, E), (V_S, V_V, E_S, E_C)$)
  + *if* $exists v in V_V$ : id($v$) = hash($o$) *then*
    + *return* $(V_S, V_V, E_S, E_C)$
  + *end*
  + \ 
  + $v arrow.l$ (hash($o$), val($o$))
  + $V_(V^') arrow.l V_V union {v}$
  + *let* $o' in O$ : ($o^', o$) $in E$
  + *let* $v' in V_V$ : id($v'$) = hash($o'$)
  + $s' arrow.l$ spec($v^'$)
  + *if* $exists s in V_S bar$ ($s', s$) $in E_C and$ name($s$) = name($o$) *then*
    + $E_(S') arrow.l E_S union {paren v, s paren.r}$
    + $V_(S') arrow.l V_S$
    + $E_(C') arrow.l E_C$
  + *else*
    + *if* $o eq$ root($O, E$) *then*
      + *if* $V_S eq emptyset$ *then*
        + $s arrow.l$ (name($o$), type(val($o$)))
        + $V_(S') arrow.l V_S union {s}$
      + *else*
        + *let* $s arrow.l$ root($V_S, E_C$)
        + $V_(S') arrow.l V_S$
      + *end*
      + $E_(C') arrow.l E_C$
    + *else*
      + $s arrow.l$ (name($o$), type(val($o$)))
      + $V_(S') arrow.l V_S union {s}$
      + $E_(C') arrow.l E_C union {paren s', s paren.r}$
    + *end*
    + $E_(S') arrow.l E_S {paren v, s paren.r}$
  + *end*

  + *foreach* $o_c in O bar paren o, o_c paren.r in E$ *do*
    + $paren V_(S'), V_(V'), E_(S'), E_(C') paren.r arrow.l$ #text(font: "New Computer Modern", features: ("smcp",), [Process-Option-Value]) ($o_c, paren O, E paren.r, paren V_(S'), V_(V'), E_(S'), E_(C') paren.r$)
    + *let* $v_c in V_(V') bar$ id($v_c$) = hash($o_c$)
    + $E_(C') arrow.l E_C union {paren v, v_c paren.r}$
  + *end*
+ *return* $paren V_(S'), V_(V'), E_(S'), E_(C') paren.r$

]
#pagebreak()
#pseudocode-list[
  #text(font: "New Computer Modern", features: ("smcp",), [Process-Option-Value]) ($o, (O, E), (V_S, V_V, E_S, E_C)$)
  + *if* $exists v in V_V$ : id($v$) = hash($o$) *then*
    + *return* $(V_S, V_V, E_S, E_C)$
  + *end*
  + \ 
  + $v arrow.l$ (hash($o$), val($o$))
  + $V_(V^') arrow.l V_V union {v}$
  + *if* $V_S eq.not emptyset and o eq$ root($O, E$) *then*
    + *let* $s arrow.l$ root($V_S, E_C$)
    + $E_(S') arrow.l E_S {paren v, s paren.r}$
  + *else*
    + *let* $o' in O$ : ($o^', o$) $in E$
    + *let* $v' in V_V$ : id($v'$) = hash($o'$)
    + $s' arrow.l$ spec($v^'$)
    + *if* $exists s in V_S bar$ ($s', s$) $in E_C and$ name($s$) = name($o$) *then*
      + $E_(S') arrow.l E_S union {paren v, s paren.r}$
      + $V_(S') arrow.l V_S$
      + $E_(C') arrow.l E_C$
    + *else*
      + $s arrow.l$ (name($o$), type(val($o$)))
      + $E_(S') arrow.l E_S {paren v, s paren.r}$
      + $V_(S') arrow.l V_S union {s}$
      + *if* $o eq.not$ root($O, E$) *then*
        + $E_(C') arrow.l E_C union {paren s', s paren.r}$
      + *else*
        + $E_(C') arrow.l E_C$
      + *end*
    + *end*
  + *end*
  + *foreach* $o_c in O bar paren o, o_c paren.r in E$ *do*
    + $paren V_(S'), V_(V'), E_(S'), E_(C') paren.r arrow.l$ #text(font: "New Computer Modern", features: ("smcp",), [Process-Option-Value]) ($o_c, paren O, E paren.r, paren V_(S'), V_(V'), E_(S'), E_(C') paren.r$)
    + *let* $v_c in V_(V') bar$ id($v_c$) = hash($o_c$)
    + $E_(C') arrow.l E_C union {paren v, v_c paren.r}$
  + *end*
+ *return* $paren V_(S'), V_(V'), E_(S'), E_(C') paren.r$
]
