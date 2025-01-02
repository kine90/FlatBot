from modules.ApplicationGenerator import ApplicationGenerator
from modules.Expose import Expose



def main():
    print("Testing Application Generator")
    expose = Expose(expose_id="00000", source = "Immobilienscout24", location = "Berlin, Tempelhof", agent_name = "Herr Piffer")

    application_generator = ApplicationGenerator()
    print(application_generator.generate_application(expose))

if __name__ == "__main__":
    main()