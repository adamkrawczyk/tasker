(define (problem DLOG-1-1-1-2-03092014122955)
  (:domain hazarddetection)
  (:objects door lamp - hazard elektron - robot initial lamp-location door-location - hazard-location )
  (:init (at elektron initial)
  		(linked lamp lamp-location)
  		(linked door door-location))
  (:goal (and (checked lamp) (checked door) (at elektron initial)))
)