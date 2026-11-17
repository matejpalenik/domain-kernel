import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashSet;

import org.semanticweb.HermiT.ReasonerFactory;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.IRI;
import org.semanticweb.owlapi.model.OWLOntology;
import org.semanticweb.owlapi.profiles.OWL2DLProfile;

/** Uses inert, validated named-class operations. This driver has no URL loader. */
class RobotOntology {
    private static OWLOntology readOntology(Path input) throws Exception {
        var manager = OWLManager.createOWLOntologyManager();
        var ontology = manager.createOntology();
        var factory = manager.getOWLDataFactory();
        try (var reader = Files.newBufferedReader(input)) {
            String line;
            while ((line = reader.readLine()) != null) {
                var columns = line.split("\t", -1);
                var first = IRI.create(columns[1]);
                var second = IRI.create(columns[2]);
                var firstClass = factory.getOWLClass(first);
                var secondClass = factory.getOWLClass(second);
                var axiom = switch (columns[0]) {
                    case "class" -> factory.getOWLDeclarationAxiom(firstClass);
                    case "individual" -> factory.getOWLDeclarationAxiom(
                        factory.getOWLNamedIndividual(first));
                    case "sub" -> factory.getOWLSubClassOfAxiom(firstClass, secondClass);
                    case "equivalent" -> factory.getOWLEquivalentClassesAxiom(firstClass, secondClass);
                    case "disjoint" -> factory.getOWLDisjointClassesAxiom(firstClass, secondClass);
                    case "member" -> factory.getOWLClassAssertionAxiom(
                        secondClass, factory.getOWLNamedIndividual(first));
                    default -> throw new IllegalArgumentException("Unknown ontology operation");
                };
                manager.addAxiom(ontology, axiom);
            }
        }
        return ontology;
    }

    public static void main(String[] args) throws Exception {
        var task = args[0];
        var ontology = readOntology(Path.of(args[1]));
        var profile = new OWL2DLProfile();
        if (!profile.checkOntology(ontology).isInProfile()) {
            System.out.println("unsupported");
            return;
        }

        var reasoner = new ReasonerFactory().createReasoner(ontology);
        try {
            if (!reasoner.isConsistent()) {
                System.out.println("inconsistent");
                return;
            }
            switch (task) {
                case "consistency" -> System.out.println("consistent");
                case "classification" -> {
                    System.out.println("consistent");
                    var signature = Files.readAllLines(Path.of(args[2]));
                    var factory = ontology.getOWLOntologyManager().getOWLDataFactory();
                    for (var iri : signature) {
                        var source = factory.getOWLClass(IRI.create(iri));
                        if (reasoner.getUnsatisfiableClasses().contains(source)) {
                            System.out.println("bottom\t" + iri);
                            continue;
                        }
                        var parents = new LinkedHashSet<>(
                            reasoner.getSuperClasses(source, false).getFlattened());
                        parents.addAll(reasoner.getEquivalentClasses(source).getEntities());
                        for (var parent : parents.stream().sorted().toList()) {
                            if (!parent.equals(source) && !parent.isOWLThing() && !parent.isOWLNothing()) {
                                System.out.println("sub\t" + iri + "\t" + parent.getIRI());
                            }
                        }
                    }
                }
                case "entailment" -> {
                    var query = readOntology(Path.of(args[2]));
                    var axioms = query.getLogicalAxioms();
                    if (!profile.checkOntology(query).isInProfile() || axioms.isEmpty()
                        || axioms.stream().anyMatch(
                            axiom -> !reasoner.isEntailmentCheckingSupported(axiom.getAxiomType()))) {
                        System.out.println("unsupported");
                    } else {
                        System.out.println(reasoner.isEntailed(axioms) ? "entailed" : "not_entailed");
                    }
                }
                default -> throw new IllegalArgumentException("Unknown reasoning task");
            }
        } finally {
            reasoner.dispose();
        }
    }
}
