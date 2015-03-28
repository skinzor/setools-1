# Copyright 2014-2015, Tresys Technology, LLC
#
# This file is part of SETools.
#
# SETools is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 2.1 of
# the License, or (at your option) any later version.
#
# SETools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with SETools.  If not, see
# <http://www.gnu.org/licenses/>.
#
import itertools
import logging
from collections import defaultdict

import networkx as nx
from networkx.exception import NetworkXError, NetworkXNoPath


class DomainTransitionAnalysis(object):

    """Domain transition analysis."""

    def __init__(self, policy, reverse=False, exclude=None):
        """
        Parameter:
        policy   The policy to analyze.
        """
        self.log = logging.getLogger(self.__class__.__name__)

        self.policy = policy
        self.set_exclude(exclude)
        self.set_reverse(reverse)
        self.rebuildgraph = True
        self.rebuildsubgraph = True
        self.G = nx.DiGraph()

    def __generate_entrypoints(self, data):
        """
        Generator which yields the entrypoint, execute, and
        type_transition rules for each entrypoint.

        Parameter:
        data     The dictionary of entrypoints.

        Yield: tuple(type, entry, exec, trans)

        type     The entrypoint type.
        entry    The list of entrypoint rules.
        exec     The list of execute rules.
        trans    The list of type_transition rules.
        """
        for e in data['entrypoint']:
            yield e, data['entrypoint'][e], data['execute'][e], data['type_transition'][e]

    def __generate_steps(self, path):
        """
        Generator which yields the source, target, and associated rules
        for each domain transition.

        Parameter:
        path     A list of graph node names representing an information flow path.

        Yield: tuple(source, target, transition, entrypoints,
                     setexec, dyntransition, setcurrent)

        source          The source type for this step of the domain transition.
        target          The target type for this step of the domain transition.
        transition      The list of transition rules.
        entrypoints     Generator which yields entrypoint-related rules.
        setexec         The list of setexec rules.
        dyntranstion    The list of dynamic transition rules.
        setcurrent      The list of setcurrent rules.
        """

        for s in range(1, len(path)):
            source = path[s - 1]
            target = path[s]

            if self.reverse:
                real_source, real_target = target, source
            else:
                real_source, real_target = source, target

            # It seems that NetworkX does not reverse the dictionaries
            # that store the attributes, so real_* is used here
            data = self.subG.edge[real_source][real_target]

            yield real_source, real_target, \
                data['transition'], \
                self.__generate_entrypoints(data), \
                data['setexec'], \
                data['dyntransition'], \
                data['setcurrent']

    def set_reverse(self, reverse):
        """
        Set forward/reverse DTA direction.

        Parameter:
        reverse     If true, a reverse DTA is performed, otherwise a
                    forward DTA is performed.
        """

        self.reverse = bool(reverse)
        self.rebuildsubgraph = True

    def set_exclude(self, exclude):
        """
        Set the domains to exclude from the domain transition analysis.

        Parameter:
        exclude         A list of types.
        """

        if exclude:
            self.exclude = [self.policy.lookup_type(t) for t in exclude]
        else:
            self.exclude = []

        self.rebuildsubgraph = True

    def shortest_path(self, source, target):
        """
        Generator which yields one shortest domain transition path
        between the source and target types (there may be more).

        Parameters:
        source  The source type.
        target  The target type.

        Yield: generator(steps)

        steps   A generator that returns the tuple of
                source, target, and rules for each
                domain transition.
        """
        s = self.policy.lookup_type(source)
        t = self.policy.lookup_type(target)

        if self.rebuildsubgraph:
            self._build_subgraph()

        self.log.info("Generating one shortest path from {0} to {1}...".format(s, t))

        try:
            yield self.__generate_steps(nx.shortest_path(self.subG, s, t))
        except (NetworkXNoPath, NetworkXError):
            # NetworkXError: the type is valid but not in graph, e.g. excluded
            # NetworkXNoPath: no paths or the target type is
            # not in the graph
            pass

    def all_paths(self, source, target, maxlen=2):
        """
        Generator which yields all domain transition paths between
        the source and target up to the specified maximum path
        length.

        Parameters:
        source   The source type.
        target   The target type.
        maxlen   Maximum length of paths.

        Yield: generator(steps)

        steps    A generator that returns the tuple of
                 source, target, and rules for each
                 domain transition.
        """
        if maxlen < 1:
            raise ValueError("Maximum path length must be positive.")

        s = self.policy.lookup_type(source)
        t = self.policy.lookup_type(target)

        if self.rebuildsubgraph:
            self._build_subgraph()

        self.log.info("Generating all paths from {0} to {1}, max len {2}...".format(s, t, maxlen))

        try:
            for p in nx.all_simple_paths(self.subG, s, t, maxlen):
                yield self.__generate_steps(p)
        except (NetworkXNoPath, NetworkXError):
            # NetworkXError: the type is valid but not in graph, e.g. excluded
            # NetworkXNoPath: no paths or the target type is
            # not in the graph
            pass

    def all_shortest_paths(self, source, target):
        """
        Generator which yields all shortest domain transition paths
        between the source and target types.

        Parameters:
        source   The source type.
        target   The target type.

        Yield: generator(steps)

        steps    A generator that returns the tuple of
                 source, target, and rules for each
                 domain transition.
        """
        s = self.policy.lookup_type(source)
        t = self.policy.lookup_type(target)

        if self.rebuildsubgraph:
            self._build_subgraph()

        self.log.info("Generating all shortest paths from {0} to {1}...".format(s, t))

        try:
            for p in nx.all_shortest_paths(self.subG, s, t):
                yield self.__generate_steps(p)
        except (NetworkXNoPath, NetworkXError, KeyError):
            # NetworkXError: the type is valid but not in graph, e.g. excluded
            # NetworkXNoPath: no paths or the target type is
            # not in the graph
            # KeyError: work around NetworkX bug
            # when the source node is not in the graph
            pass

    def transitions(self, type_):
        """
        Generator which yields all domain transitions out of a
        specified source type.

        Parameters:
        type_   The starting type.

        Yield: generator(steps)

        steps   A generator that returns the tuple of
                source, target, and rules for each
                domain transition.
        """
        s = self.policy.lookup_type(type_)

        if self.rebuildsubgraph:
            self._build_subgraph()

        self.log.info("Generating all transitions {1} {0}".
                      format(s, "in to" if self.reverse else "out from"))

        try:
            for source, target in self.subG.out_edges_iter(s):
                if self.reverse:
                    real_source, real_target = target, source
                else:
                    real_source, real_target = source, target

                # It seems that NetworkX does not reverse the dictionaries
                # that store the attributes, so real_* is used here
                data = self.subG.edge[real_source][real_target]

                yield real_source, real_target, \
                    data['transition'], \
                    self.__generate_entrypoints(data), \
                    data['setexec'], \
                    data['dyntransition'], \
                    data['setcurrent']
        except NetworkXError:
            # NetworkXError: the type is valid but not in graph, e.g. excluded
            pass

    def get_stats(self):  # pragma: no cover
        """
        Get the domain transition graph statistics.

        Return:  tuple(nodes, edges)

        nodes    The number of nodes (types) in the graph.
        edges    The number of edges (domain transitions) in the graph.
        """
        return (self.G.number_of_nodes(), self.G.number_of_edges())

    # Graph edge properties:
    # Each entry in the property dict corresponds to
    # a rule list.  For entrypoint/execute/type_transition
    # it is a dictionary keyed on the entrypoint type.
    def __add_edge(self, source, target):
        self.G.add_edge(source, target)
        if 'transition' not in self.G[source][target]:
            self.G[source][target]['transition'] = []
        if 'entrypoint' not in self.G[source][target]:
            self.G[source][target]['entrypoint'] = defaultdict(list)
        if 'execute' not in self.G[source][target]:
            self.G[source][target]['execute'] = defaultdict(list)
        if 'type_transition' not in self.G[source][target]:
            self.G[source][target]['type_transition'] = defaultdict(list)
        if 'setexec' not in self.G[source][target]:
            self.G[source][target]['setexec'] = []
        if 'dyntransition' not in self.G[source][target]:
            self.G[source][target]['dyntransition'] = []
        if 'setcurrent' not in self.G[source][target]:
            self.G[source][target]['setcurrent'] = []

    # Domain transition requirements:
    #
    # Standard transitions a->b:
    # allow a b:process transition;
    # allow a b_exec:file execute;
    # allow b b_exec:file entrypoint;
    #
    # and at least one of:
    # allow a self:process setexec;
    # type_transition a b_exec:process b;
    #
    # Dynamic transition x->y:
    # allow x y:process dyntransition;
    # allow x self:process setcurrent;
    #
    # Algorithm summary:
    # 1. iterate over all rules
    #   1. skip non allow/type_transition rules
    #   2. if process transition or dyntransition, create edge,
    #      initialize rule lists, add the (dyn)transition rule
    #   3. if process setexec or setcurrent, add to appropriate dict
    #      keyed on the subject
    #   4. if file exec, entrypoint, or type_transition:process,
    #      add to appropriate dict keyed on subject,object.
    # 2. Iterate over all graph edges:
    #   1. if there is a transition rule (else add to invalid
    #      transition list):
    #       1. use set intersection to find matching exec
    #          and entrypoint rules. If none, add to invalid
    #          transition list.
    #       2. for each valid entrypoint, add rules to the
    #          edge's lists if there is either a
    #          type_transition for it or the source process
    #          has setexec permissions.
    #       3. If there are neither type_transitions nor
    #          setexec permissions, add to the invalid
    #          transition list
    #   2. if there is a dyntransition rule (else add to invalid
    #      dyntrans list):
    #       1. If the source has a setcurrent rule, add it
    #          to the edge's list, else add to invalid
    #          dyntransition list.
    # 3. Iterate over all graph edges:
    #   1. if the edge has an invalid trans and dyntrans, delete
    #      the edge.
    #   2. if the edge has an invalid trans, clear the related
    #      lists on the edge.
    #   3. if the edge has an invalid dyntrans, clear the related
    #      lists on the edge.
    #
    def _build_graph(self):
        self.G.clear()

        self.log.info("Building graph from {0}...".format(self.policy))

        # hash tables keyed on domain type
        setexec = defaultdict(list)
        setcurrent = defaultdict(list)

        # hash tables keyed on (domain, entrypoint file type)
        # the parameter for defaultdict has to be callable
        # hence the lambda for the nested defaultdict
        execute = defaultdict(lambda: defaultdict(list))
        entrypoint = defaultdict(lambda: defaultdict(list))

        # hash table keyed on (domain, entrypoint, target domain)
        type_trans = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

        for r in self.policy.terules():
            if r.ruletype == "allow":
                if r.tclass not in ["process", "file"]:
                    continue

                perms = r.perms

                if r.tclass == "process":
                    if "transition" in perms:
                        for s, t in itertools.product(r.source.expand(), r.target.expand()):
                            # only add edges if they actually
                            # transition to a new type
                            if s != t:
                                self.__add_edge(s, t)
                                self.G[s][t]['transition'].append(r)

                    if "dyntransition" in perms:
                        for s, t in itertools.product(r.source.expand(), r.target.expand()):
                            # only add edges if they actually
                            # transition to a new type
                            if s != t:
                                self.__add_edge(s, t)
                                self.G[s][t]['dyntransition'].append(r)

                    if "setexec" in perms:
                        for s in r.source.expand():
                            setexec[s].append(r)

                    if "setcurrent" in perms:
                        for s in r.source.expand():
                            setcurrent[s].append(r)

                else:
                    if "execute" in perms:
                        for s, t in itertools.product(
                                r.source.expand(),
                                r.target.expand()):
                            execute[s][t].append(r)

                    if "entrypoint" in perms:
                        for s, t in itertools.product(r.source.expand(), r.target.expand()):
                            entrypoint[s][t].append(r)

            elif r.ruletype == "type_transition":
                if r.tclass != "process":
                    continue

                d = r.default
                for s, t in itertools.product(r.source.expand(), r.target.expand()):
                    type_trans[s][t][d].append(r)

        invalid_edge = []
        clear_transition = []
        clear_dyntransition = []

        for s, t in self.G.edges_iter():
            invalid_trans = False
            invalid_dyntrans = False

            if self.G[s][t]['transition']:
                # get matching domain exec w/entrypoint type
                entry = set(entrypoint[t].keys())
                exe = set(execute[s].keys())
                match = entry.intersection(exe)

                if not match:
                    # there are no valid entrypoints
                    invalid_trans = True
                else:
                    # TODO try to improve the
                    # efficiency in this loop
                    for m in match:
                        if s in setexec or type_trans[s][m]:
                            # add subkey for each entrypoint
                            self.G[s][t]['entrypoint'][m] += entrypoint[t][m]
                            self.G[s][t]['execute'][m] += execute[s][m]

                        if type_trans[s][m][t]:
                            self.G[s][t]['type_transition'][m] += type_trans[s][m][t]

                    if s in setexec:
                        self.G[s][t]['setexec'] += setexec[s]

                    if not self.G[s][t]['setexec'] and not self.G[s][t]['type_transition']:
                        invalid_trans = True
            else:
                invalid_trans = True

            if self.G[s][t]['dyntransition']:
                if s in setcurrent:
                    self.G[s][t]['setcurrent'] += setcurrent[s]
                else:
                    invalid_dyntrans = True
            else:
                invalid_dyntrans = True

            # cannot change the edges while iterating over them,
            # so keep appropriate lists
            if invalid_trans and invalid_dyntrans:
                invalid_edge.append((s, t))
            elif invalid_trans:
                clear_transition.append((s, t))
            elif invalid_dyntrans:
                clear_dyntransition.append((s, t))

        # Remove invalid transitions
        self.G.remove_edges_from(invalid_edge)
        for s, t in clear_transition:
            # if only the regular transition is invalid,
            # clear the relevant lists
            del self.G[s][t]['transition'][:]
            self.G[s][t]['execute'].clear()
            self.G[s][t]['entrypoint'].clear()
            self.G[s][t]['type_transition'].clear()
            del self.G[s][t]['setexec'][:]
        for s, t in clear_dyntransition:
            # if only the dynamic transition is invalid,
            # clear the relevant lists
            del self.G[s][t]['dyntransition'][:]
            del self.G[s][t]['setcurrent'][:]

        self.rebuildgraph = False
        self.rebuildsubgraph = True
        self.log.info("Completed building graph.")

    def __remove_excluded_entrypoints(self):
        invalid_edges = []
        for source, target in self.subG.edges_iter():
            entrypoints = set(self.subG.edge[source][target]['entrypoint'])
            entrypoints.intersection_update(self.exclude)

            if not entrypoints:
                # short circuit if there are no
                # excluded entrypoint types on
                # this edge.
                continue

            for e in entrypoints:
                # clear the entrypoint data
                del self.subG.edge[source][target]['entrypoint'][e]
                del self.subG.edge[source][target]['execute'][e]

                try:
                    del self.subG.edge[source][target]['type_transition'][e]
                except KeyError:  # setexec
                    pass

            # cannot change the edges while iterating over them
            if len(self.subG.edge[source][target]['entrypoint']) == 0 and \
                    len(self.subG.edge[source][target]['dyntransition']) == 0:
                invalid_edges.append((source, target))

        self.subG.remove_edges_from(invalid_edges)

    def _build_subgraph(self):
        if self.rebuildgraph:
            self._build_graph()

        self.log.info("Building subgraph.")
        self.log.debug("Excluding {0}".format(self.exclude))
        self.log.debug("Reverse {0}".format(self.reverse))

        # delete excluded domains from subgraph
        nodes = [n for n in self.G.nodes() if n not in self.exclude]
        # subgraph created this way to get copies of the edge
        # attributes. otherwise the edge attributes point to the
        # original graph, and the entrypoint removal below would also
        # affect the main graph.
        self.subG = nx.DiGraph(self.G.subgraph(nodes))

        # delete excluded entrypoints from subgraph
        if self.exclude:
            self.__remove_excluded_entrypoints()

        # reverse graph for reverse DTA
        if self.reverse:
            self.subG.reverse(copy=False)

        self.rebuildsubgraph = False
        self.log.info("Completed building subgraph.")
