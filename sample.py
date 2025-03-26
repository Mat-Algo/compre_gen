from manim_voiceover import VoiceoverScene
from manim_voiceover.services.elevenlabs import ElevenLabsService
from manim import *

class AdvancedIntegrationVoiceoverScene(VoiceoverScene):
    def construct(self):
        self.set_speech_service(ElevenLabsService(voice_id="21m00Tcm4TlvDq8ikWAM"))

        title = Text("Advanced Integration Techniques", color=BLUE).scale(1.2)
        self.play(Write(title))
        self.wait(1)

        with self.voiceover(text="Let's explore some advanced techniques for solving integrals, building upon the fundamentals of calculus."):
            pass

        self.play(FadeOut(title))

        # 1. Integration by Parts
        integration_by_parts = MathTex(r"\int u \, dv = uv - \int v \, du").scale(1.2)
        self.play(Write(integration_by_parts))
        self.wait(1)

        with self.voiceover(text="First up, we have Integration by Parts. This technique is useful for integrating products of functions."):
            pass

        example_ibp = MathTex(r"\int x \sin(x) \, dx").next_to(integration_by_parts, DOWN, buff=0.5)
        self.play(Write(example_ibp))
        self.wait(1)

        with self.voiceover(text="For example, consider the integral of x times sin(x).  We can choose u as x and dv as sin(x) dx."):
            pass
        
        solution_ibp = MathTex(r" = -x \cos(x) + \int \cos(x) \, dx = -x \cos(x) + \sin(x) + C").next_to(example_ibp, DOWN, buff=0.5)
        self.play(Write(solution_ibp))
        self.wait(2)

        with self.voiceover(text="Applying the formula gives us minus x cos(x) plus the integral of cos(x), which simplifies to minus x cos(x) plus sin(x) plus a constant of integration."):
            pass

        self.play(FadeOut(integration_by_parts), FadeOut(example_ibp), FadeOut(solution_ibp))

        # 2. Trigonometric Substitution
        trig_sub = MathTex(r"\text{Trigonometric Substitution}").scale(1.2)
        self.play(Write(trig_sub))
        self.wait(1)

        with self.voiceover(text="Next, we have Trigonometric Substitution. This is effective when dealing with integrals containing square roots of the form a squared minus x squared, a squared plus x squared, or x squared minus a squared."):
            pass

        example_trig = MathTex(r"\int \sqrt{a^2 - x^2} \, dx").next_to(trig_sub, DOWN, buff=0.5)
        self.play(Write(example_trig))
        self.wait(1)

        with self.voiceover(text="Consider the integral of the square root of a squared minus x squared. Here, we can substitute x equals a times sin(theta)."):
            pass
        
        substitution = MathTex(r"x = a \sin(\theta)").next_to(example_trig, DOWN, buff=0.5)
        self.play(Write(substitution))
        self.wait(2)

        with self.voiceover(text="After applying this substitution and simplifying, we can solve the integral in terms of theta and then substitute back to get the result in terms of x."):
            pass

        self.play(FadeOut(trig_sub), FadeOut(example_trig), FadeOut(substitution))

        # 3. Partial Fraction Decomposition
        partial_fractions = MathTex(r"\text{Partial Fraction Decomposition}").scale(1.2)
        self.play(Write(partial_fractions))
        self.wait(1)

        with self.voiceover(text="Lastly, we have Partial Fraction Decomposition. This technique is used to integrate rational functions where the degree of the numerator is less than the degree of the denominator."):
            pass

        example_pfd = MathTex(r"\int \frac{1}{x^2 - 1} \, dx").next_to(partial_fractions, DOWN, buff=0.5)
        self.play(Write(example_pfd))
        self.wait(1)

        with self.voiceover(text="For instance, consider integrating one over x squared minus one. We can decompose this into partial fractions. "):
            pass

        decomposition = MathTex(r"\frac{1}{x^2 - 1} = \frac{A}{x - 1} + \frac{B}{x + 1}").next_to(example_pfd, DOWN, buff=0.5)
        self.play(Write(decomposition))
        self.wait(2)

        with self.voiceover(text="By finding the values of A and B, we can rewrite the integral as a sum of simpler integrals that are easier to solve. After solving each term separately, we obtain the final solution."):
            pass
        
        self.play(FadeOut(partial_fractions), FadeOut(example_pfd), FadeOut(decomposition))

        summary = Text("These are just a few advanced integration techniques. Practice is key!", color=GREEN).scale(1)
        self.play(Write(summary))
        self.wait(3)

        with self.voiceover(text="These are just a few of the many advanced integration techniques available.  Practice is key to mastering them. Good luck!"):
            pass
            
        self.play(FadeOut(summary))
        self.wait(1)