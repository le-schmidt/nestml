stdp_nn_restr_symm
##################


Synapse type for spike-timing dependent plasticity with restricted symmetric nearest-neighbour spike pairing scheme

Description
+++++++++++

stdp_nn_restr_synapse is a connector to create synapses with spike time
dependent plasticity with the restricted symmetric nearest-neighbour spike
pairing scheme (fig. 7C in [1]_).

When a presynaptic spike occurs, it is taken into account in the depression
part of the STDP weight change rule with the nearest preceding postsynaptic
one, but only if the latter occured not earlier than the previous presynaptic
one. When a postsynaptic spike occurs, it is accounted in the facilitation
rule with the nearest preceding presynaptic one, but only if the latter
occured not earlier than the previous postsynaptic one. So, a spike can
participate neither in two depression pairs nor in two potentiation pairs.
The pairs exactly coinciding (so that presynaptic_spike == postsynaptic_spike
+ dendritic_delay), leading to zero delta_t, are discarded. In this case the
concerned pre/postsynaptic spike is paired with the second latest preceding
post/presynaptic one (for example, pre=={10 ms; 20 ms} and post=={20 ms} will
result in a potentiation pair 20-to-10).

The implementation relies on an additional variable - the postsynaptic
eligibility trace [1]_ (implemented on the postsynaptic neuron side). It
decays exponentially with the time constant tau_minus and increases to 1 on
a post-spike occurrence (instead of increasing by 1 as in stdp_synapse).

.. figure:: https://raw.githubusercontent.com/nest/nestml/master/doc/fig/stdp-nearest-neighbour.png

   Figure 7 from Morrison, Diesmann and Gerstner

   Original caption:

   Phenomenological models of synaptic plasticity based on spike timing", Biological Cybernetics 98 (2008). "Examples of nearest neighbor spike pairing schemes for a pre-synaptic neuron j and a postsynaptic neuron i. In each case, the dark gray indicate which pairings contribute toward depression of a synapse, and light gray indicate which pairings contribute toward potentiation. **(a)** Symmetric interpretation: each presynaptic spike is paired with the last postsynaptic spike, and each postsynaptic spike is paired with the last presynaptic spike (Morrison et al. 2007). **(b)** Presynaptic centered interpretation: each presynaptic spike is paired with the last postsynaptic spike and the next postsynaptic spike (Izhikevich and Desai 2003; Burkitt et al. 2004: Model II). **(c)** Reduced symmetric interpretation: as in **(b)** but only for immediate pairings (Burkitt et al. 2004: Model IV, also implemented in hardware by Schemmel et al. 2006)

References
++++++++++

.. [1] Morrison A., Diesmann M., and Gerstner W. (2008) Phenomenological
       models of synaptic plasticity based on spike timing,
       Biol. Cybern. 98, 459--478



Parameters
++++++++++



.. csv-table::
    :header: "Name", "Physical unit", "Default value", "Description"
    :widths: auto

    
    "the_delay", "ms", "1ms", "!!! cannot have a variable called ""delay"""    
    "lambda", "real", "0.01", ""    
    "tau_tr_pre", "ms", "20ms", ""    
    "tau_tr_post", "ms", "20ms", ""    
    "alpha", "real", "1.0", ""    
    "mu_plus", "real", "1.0", ""    
    "mu_minus", "real", "1.0", ""    
    "Wmax", "real", "100.0", ""    
    "Wmin", "real", "0.0", ""



State variables
+++++++++++++++

.. csv-table::
    :header: "Name", "Physical unit", "Default value", "Description"
    :widths: auto

    
    "w", "real", "1.0", ""    
    "pre_trace", "real", "0.0", ""    
    "post_trace", "real", "0.0", ""    
    "pre_handled", "boolean", "true", ""
Source code
+++++++++++

.. code-block:: nestml

   synapse stdp_nn_restr_symm:
     state:
       w real = 1.0
       pre_trace real = 0.0
       post_trace real = 0.0
       pre_handled boolean = true
     end
     parameters:
       the_delay ms = 1ms # !!! cannot have a variable called "delay"
       lambda real = 0.01
       tau_tr_pre ms = 20ms
       tau_tr_post ms = 20ms
       alpha real = 1.0
       mu_plus real = 1.0
       mu_minus real = 1.0
       Wmax real = 100.0
       Wmin real = 0.0
     end
     equations:
       # nearest-neighbour trace of presynaptic neuron
       pre_trace'=-pre_trace / tau_tr_pre
       # nearest-neighbour trace of postsynaptic neuron
       post_trace'=-post_trace / tau_tr_post
     end

     input:
       pre_spikes nS <-spike
       post_spikes nS <-spike
     end

     output: spike

     onReceive(post_spikes):
       post_trace = 1
       # potentiate synapse
       if not pre_handled:
         w_ real = Wmax * (w / Wmax + (lambda * (1.0 - (w / Wmax)) ** mu_plus * pre_trace))
         w = min(Wmax,w_)
         pre_handled = true
       end
     end

     onReceive(pre_spikes):
       pre_trace = 1
       # depress synapse
       if pre_handled:
         w_ real = Wmax * (w / Wmax - (alpha * lambda * (w / Wmax) ** mu_minus * post_trace))
         w = max(Wmin,w_)
       end
       pre_handled = false
       # deliver spike to postsynaptic partner
       deliver_spike(w,the_delay)
     end

   end



Characterisation
++++++++++++++++

.. include:: stdp_nn_restr_symm_characterisation.rst


.. footer::

   Generated at 2021-12-09 08:22:33.039457
